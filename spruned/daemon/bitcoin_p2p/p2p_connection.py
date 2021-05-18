import asyncio
from asyncio import IncompleteReadError

import aiohttp_socks
import async_timeout
import time

import typing

from spruned.application.logging_factory import Logger
from spruned.application.tools import check_internet_connection, async_delayed_task
from spruned.daemon import exceptions
from spruned.daemon.bitcoin_p2p import save_p2p_peers
from spruned.daemon.connection_base_impl import BaseConnection
from spruned.daemon.connectionpool_base_impl import BaseConnectionPool
from spruned.daemon.exceptions import PeerBlockchainBehindException, PeerVersionMismatchException
from spruned.dependencies.pycoinnet.Peer import Peer
from spruned.dependencies.pycoinnet.PeerEvent import PeerEvent
from spruned.dependencies.pycoinnet.inv_batcher import InvBatcher
from spruned.dependencies.pycoinnet.networks import MAINNET, Network
from spruned.dependencies.pycoinnet.pycoin import InvItem
from spruned.dependencies.pycoinnet.pycoin.InvItem import ITEM_TYPE_TX
from spruned.dependencies.pycoinnet.pycoin.bloom import BloomFilter, filter_size_required, hash_function_count_required
from spruned.dependencies.pycoinnet.version import version_data_for_peer, NODE_NONE, NODE_WITNESS


def connector_f(host: str = None, port: int = None, proxy: str = None):
    if proxy:
        return aiohttp_socks.open_connection(socks_url=proxy, host=host, port=port)
    return asyncio.open_connection(host=host, port=port)


class P2PConnection(BaseConnection):
    def ping(self, timeout=None):
        self.peer.send_msg('ping', int(time.time()))

    def __init__(
            self,
            hostname: str,
            port: int,
            peer=Peer,
            network: Network = MAINNET,
            loop=asyncio.get_event_loop(),
            proxy: typing.Optional[str] = None,
            start_score: int = 10,
            is_online_checker: typing.Optional[callable] = None,
            timeout: int = 10,
            delayer: callable = async_delayed_task,
            expire_errors_after: int = 180,
            call_timeout: int = 5,
            connector: callable = connector_f,
            bloom_filter=None,
            best_header: typing.Dict = None,
            version_checker: callable = None
    ):

        super().__init__(
            hostname=hostname,
            proxy=proxy,
            loop=loop,
            start_score=start_score,
            is_online_checker=is_online_checker,
            timeout=timeout,
            delayer=delayer,
            expire_errors_after=expire_errors_after
        )
        self._bloom_filter = bloom_filter
        self.port = port
        self._peer_factory = peer
        self._peer_network = network
        self.peer = None
        self._version = None
        self.loop = loop
        self._event_handler = None
        self._call_timeout = call_timeout
        self._on_block_callbacks = []
        self._on_transaction_callbacks = []
        self._on_transaction_hash_callbacks = []
        self._on_addr_callbacks = []
        self.connector = connector
        self.best_header = best_header
        self.starting_height = None
        self.version_checker = version_checker
        self.failed = False
        self._antispam = []
        self.current_pool = None

    @property
    def proxy(self):
        proxy = self._proxy and self._proxy.split(':')
        return proxy and len(proxy) > 1 and 'socks5://{}:{}'.format(proxy[0], proxy[1])

    @property
    def subversion(self):
        return self._version and self._version.get('subversion', b'').decode().strip('/')

    @property
    def connected(self):
        return bool(self.peer)

    def add_on_blocks_callback(self, callback: callable):
        self._on_block_callbacks.append(callback)

    def add_on_transaction_hash_callback(self, callback: callable):
        self._on_transaction_hash_callbacks.append(callback)

    def add_on_transaction_callback(self, callback: callable):
        self._on_transaction_callbacks.append(callback)

    def add_on_addr_callback(self, callback: callable):
        self._on_addr_callbacks.append(callback)

    @property
    def peer_event_handler(self) -> PeerEvent:
        return self._event_handler

    def add_error(self, *a, origin=None):
        super().add_error(*a, origin=origin)
        Logger.p2p.error('Adding error to connection, origin: %s, score: %s', origin, self.score)
        if self.score <= 0:
            self.loop.create_task(self.disconnect())

    def add_success(self):
        self._score += 1

    async def _handle_connect(self):
        reader, writer = await self.connector(host=self.hostname, port=self.port, proxy=self.proxy)
        peer = self._peer_factory(
            reader,
            writer,
            self._peer_network.magic_header,
            self._peer_network.parse_from_data,
            self._peer_network.pack_from_data
        )
        version_msg = version_data_for_peer(
            peer, version=70015, local_services=NODE_NONE, remote_services=NODE_WITNESS,
            relay=self.current_pool.enable_mempool
        )
        version_data = await self._verify_peer(await peer.perform_handshake(**version_msg))
        self.starting_height = version_data['last_block_index']
        if self._bloom_filter:
            filter_bytes, hash_function_count, tweak = self._bloom_filter.filter_load_params()
            flags = 0
            peer.send_msg(
                "filterload",
                filter=filter_bytes,
                hash_function_count=hash_function_count,
                tweak=tweak,
                flags=flags
            )

        self._event_handler = PeerEvent(peer)
        self._version = version_data

        Logger.p2p.info(
            'Connected to peer %s:%s (%s)', self.hostname, self.port,
            self.version and self.version.get('subversion', b'').decode().strip('/')
        )
        Logger.p2p.debug('Peer raw response %s', self.version)
        self.peer = peer
        self.connected_at = int(time.time())
        self._setup_events_handler()

    async def connect(self):
        try:
            async with async_timeout.timeout(5):
                await self._handle_connect()
        except (
                ConnectionResetError,
                ConnectionRefusedError,
                OSError,
                PeerBlockchainBehindException,
                asyncio.TimeoutError,
                PeerVersionMismatchException,
                IncompleteReadError
        ) as e:
            if isinstance(e, OSError) and 'Connect call failed' not in str(e):
                raise e
            Logger.p2p.debug('Exception connecting to %s (%s)', self.hostname, str(e))
            self._on_connection_failed()
            return

        except Exception as e:
            Logger.p2p.exception('Exception connecting to %s (%s)', self.hostname, str(e))
            self._on_connection_failed()
            return

        self.loop.create_task(self.on_connect())
        return self

    def _on_connection_failed(self):
        self.peer = None
        self.failed = True
        self.loop.create_task(self.on_error('connect'))
        return

    async def _verify_peer(self, version_data: typing.Dict):
        if self.best_header and self.best_header['block_height'] - version_data['last_block_index'] > 5:
            await self.disconnect()
            raise exceptions.PeerVersionMismatchException
        if self.version_checker and not self.version_checker(version_data):
            await self.disconnect()
            raise exceptions.PeerBlockchainBehindException
        return version_data

    async def on_connect(self):
        for callback in self._on_connect_callbacks:
            self.loop.create_task(callback(self))

    async def disconnect(self):
        try:
            Logger.p2p.debug(
                'Disconnecting peer %s (%s)' % (self.hostname, self.version and self.version.get('subversion'))
            )
            self.current_pool.connections.remove(self)
            self.peer and self.peer.close()
        except ValueError:
            pass
        finally:
            self.peer = None
            self.failed = True

    def _setup_events_handler(self):
        self.peer_event_handler.set_request_callback('inv', self._on_inv)
        self.peer_event_handler.set_request_callback('addr', self._on_addr)
        self.peer_event_handler.set_request_callback('alert', self._on_alert)
        self.peer_event_handler.set_request_callback('ping', self._on_ping)
        self.peer_event_handler.set_request_callback('sendheaders', self._dummy_handler)
        self.peer_event_handler.set_request_callback('feefilter', self._dummy_handler)
        self.peer_event_handler.set_request_callback('sendcmpct', self._dummy_handler)
        self.peer_event_handler.set_request_callback('tx', self._on_tx_inv)

    def _dummy_handler(self, *a, **kw):
        pass

    def _on_tx_inv(self, event_handler: PeerEvent, name: str, data: typing.Dict):
        for callback in self._on_transaction_callbacks:
            self.loop.create_task(callback(self, data))

    def _on_inv(self, event_handler: PeerEvent, name: str, data: typing.Dict):
        self.loop.create_task(self._process_inv(event_handler, name, data))

    @staticmethod
    def _on_alert(event_handler: PeerEvent, name: str, data: typing.Dict):  # pragma: no cover
        Logger.p2p.debug('Handle alert: %s, %s, %s', event_handler, name, data)

    def _on_addr(self, event_handler: PeerEvent, name: str, data: typing.Dict):  # pragma: no cover
        try:
            peers = []
            for peer in data['date_address_tuples']:
                host, port = str(peer[1]).split('/')
                port = int(port)
                peers.append([host, port])
            for callback in self._on_addr_callbacks:
                self.loop.create_task(callback(peers))
        except:
            Logger.p2p.exception('Exception on addr')

    def _on_ping(self, event_handler: PeerEvent, name: str, data: typing.Dict):
        try:
            self.peer.send_msg("pong", nonce=data["nonce"])
            Logger.p2p.debug('Handle ping: %s, %s, %s', event_handler, name, data)
        except:
            Logger.p2p.exception('Exception on ping')

    async def _process_inv(self, event_handler: PeerEvent, name: str, data: typing.Dict):
        txs = 0
        for item in data.get('items'):
            if item.item_type == ITEM_TYPE_TX:
                txs += 1
                for callback in self._on_transaction_hash_callbacks:
                    self.loop.create_task(callback(self, item))
            else:
                Logger.p2p.debug('Unhandled InvType: %s, %s, %s', event_handler, name, item)
        Logger.p2p.debug('Received %s items, txs: %s', len(data.get('items')), txs)

    async def getaddr(self):
        self.peer.send_msg("getaddr")


class P2PConnectionPool(BaseConnectionPool):
    async def on_peer_received_peers(self, peer, *a):
        Logger.p2p.debug('Received peers from peer: %s: (%s)', peer.hostname, a)

    def __init__(
            self,
            peers=None,
            network_checker=check_internet_connection,
            delayer=async_delayed_task,
            loop=asyncio.get_event_loop(),
            proxy=False,
            connections=3,
            sleep_no_internet=30,
            batcher=InvBatcher,
            network=MAINNET,
            batcher_timeout=30,
            ipv6=False,
            servers_storage=save_p2p_peers,
            context=None,
            enable_mempool=False,
            max_peers_per_request=4
    ):
        super().__init__(
            peers=peers or [], network_checker=network_checker, delayer=delayer, ipv6=ipv6,
            loop=loop, proxy=proxy, connections=connections, sleep_no_internet=sleep_no_internet
        )
        self.max_peers_per_request = max_peers_per_request
        self._pool_filter = None
        self._batcher_factory = batcher
        self._network = network
        self._batcher_timeout = batcher_timeout
        self._busy_peers = set()
        self.servers_storage = servers_storage
        self._storage_lock = asyncio.Lock()
        self._required_connections = connections
        self.best_header = None
        self._on_transaction_hash_callback = []
        self._on_transaction_callback = []
        self._on_block_callback = []
        self.context = context
        self.enable_mempool = enable_mempool

    @property
    def busy_peers(self):
        return self._busy_peers

    @property
    def proxy(self):
        return self._proxy

    async def set_best_header(self, value: typing.Dict):
        self.best_header = value

    def _create_bloom_filter(self):
        element_count = 1
        false_positive_probability = 0.00001
        filter_size = filter_size_required(element_count, false_positive_probability)
        hash_function_count = hash_function_count_required(filter_size, element_count)
        self._pool_filter = BloomFilter(filter_size, hash_function_count=hash_function_count, tweak=1)
        self._pool_filter.add_address('1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa')

    def version_checker(self, peer_version: typing.Dict):
        return self.context.get_network()['evaluate_peer_version'](peer_version)

    @property
    def required_connections(self):
        return self._required_connections

    @property
    def available(self):
        return len(self.connections) >= self._required_connections

    def add_peer(self, peer):
        self._peers.append(peer)

    def add_on_transaction_hash_callback(self, callback):
        self._on_transaction_hash_callback.append(callback)

    def add_on_transaction_callback(self, callback):
        self._on_transaction_callback.append(callback)

    def add_on_block_callback(self, callback):
        self._on_block_callback.append(callback)

    @property
    def connections(self):
        for connection in self._connections:
            if connection.failed:
                del connection
        return self._connections

    async def connect(self):
        await self._check_internet_connectivity()
        self._keepalive = True
        while not self._peers:
            Logger.p2p.warning('Peers not loaded yet')
            await asyncio.sleep(1)

        while self._keepalive:
            if not self.is_online():
                Logger.p2p.error(
                    'Looks like there is no internet connection available. '
                    'Sleeping the connection loop for %s',
                    self._sleep_on_no_internet_connectivity
                )
                await asyncio.sleep(self._sleep_on_no_internet_connectivity)
                await self._check_internet_connectivity()
                continue
            missing = min(16, self._required_connections - len(self.established_connections))
            if missing > 0:
                peers = self._pick_multiple_peers(missing)
                for peer in peers:
                    host, port = peer
                    self.loop.create_task(self._connect_peer(host, port))
            elif len(self.established_connections) > self._required_connections:
                Logger.p2p.warning('Too many connections')
                connection = self._pick_connection()
                self.loop.create_task(connection.disconnect())
            for connection in self._connections:
                if connection.score <= 0:
                    Logger.p2p.debug('Disconnecting peer with score 0: %s', connection.hostname)
                    self.loop.create_task(self._disconnect_peer(connection))
            await asyncio.sleep(1)

    @staticmethod
    async def _disconnect_peer(connection: P2PConnection):
        await connection.disconnect()

    async def _connect_peer(self, host: str, port: int):
        connection = P2PConnection(
            host, port, loop=self.loop, network=self._network,
            bloom_filter=self._pool_filter, best_header=self.best_header,
            version_checker=self.version_checker, proxy=self._proxy
        )
        connection.current_pool = self
        if not await connection.connect():
            Logger.p2p.debug(
                'Connection to %s - %s failed. Connected to %s peers', host, port, len(self.established_connections)
            )
            return
        self._connections.append(connection)
        connection.add_on_connect_callback(self.on_peer_connected)
        connection.add_on_header_callbacks(self.on_peer_received_header)
        connection.add_on_peers_callback(self.on_peer_received_peers)
        connection.add_on_error_callback(self.on_peer_error)
        connection.add_on_addr_callback(self.save_peers)
        for callback in self._on_transaction_hash_callback:
            connection.add_on_transaction_hash_callback(callback)
        for callback in self._on_transaction_callback:
            connection.add_on_transaction_callback(callback)
        for callback in self._on_block_callback:
            connection.add_on_blocks_callback(callback)

    async def get(self, inv_item: InvItem, peers=None, timeout=None, privileged=False):
        batcher = self._batcher_factory(target_batch_time=self._batcher_timeout)
        connections = []
        s = time.time()
        Logger.p2p.debug('Fetching InvItem %s', inv_item)
        try:
            connections = privileged and self._pick_privileged_connections(
                peers if peers is not None else (min(self.max_peers_per_request, len(self.established_connections)))
            ) or []
            connections = connections or self._pick_multiple_connections(
                peers if peers is not None else (min(self.max_peers_per_request, len(self.established_connections)))
            )
            for connection in connections:
                await batcher.add_peer(connection.peer_event_handler)
            future = await batcher.inv_item_to_future(inv_item)
            while not future.done():
                if time.time() - s > min((x for x in (timeout, self._batcher_timeout) if x)):
                    Logger.p2p.debug(
                        'Error in get InvItem %s, failed in %ss from peers %s',
                        inv_item, round(time.time() - s, 4),
                        ', '.join(['{} ({})'.format(x.hostname, len(x.errors)) for x in connections])
                    )
                    future.cancel()
                    for connection in connections:
                        connection.add_error(origin='get InvItem')
                    return
                await asyncio.sleep(0.01)
            response = future.result()
            Logger.p2p.debug('InvItem %s fetched in %ss', inv_item, round(time.time() - s, 4))
            for connection in connections:
                connection.add_success()
            return response and response
        finally:
            self._clean_connections(connections)

    def _clean_connections(self, connections: typing.List[P2PConnection]):
        for connection in connections:
            try:
                self._busy_peers.remove(connection.hostname)
            except KeyError:
                pass

    @staticmethod
    async def on_peer_connected(connection: P2PConnection):
        Logger.p2p.debug('on_peer_connected: %s', connection.hostname)
        await connection.getaddr()

    async def save_peers(self, data):
        await self._storage_lock.acquire()
        try:
            self._peers = self.servers_storage(data)
        finally:
            self._storage_lock.release()

    async def get_from_connection(self, connection: P2PConnection, inv_item):
        batcher = self._batcher_factory()
        await batcher.add_peer(connection.peer_event_handler)
        future = None
        try:
            future = await batcher.inv_item_to_future(inv_item)
            response = await future
            return response
        finally:
            future and future.cancel()
