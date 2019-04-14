import asyncio

import aiohttp_socks
import async_timeout
import time

from spruned.application.logging_factory import Logger
from spruned.application.tools import check_internet_connection, async_delayed_task
from spruned.daemon import exceptions
from spruned.daemon.bitcoin_p2p import save_p2p_peers
from spruned.daemon.connection_base_impl import BaseConnection
from spruned.daemon.connectionpool_base_impl import BaseConnectionPool
from spruned.dependencies.pycoinnet.Peer import Peer
from spruned.dependencies.pycoinnet.PeerEvent import PeerEvent
from spruned.dependencies.pycoinnet.inv_batcher import InvBatcher
from spruned.dependencies.pycoinnet.networks import MAINNET
from spruned.dependencies.pycoinnet.pycoin import InvItem
from spruned.dependencies.pycoinnet.pycoin.InvItem import ITEM_TYPE_TX
from spruned.dependencies.pycoinnet.pycoin.bloom import BloomFilter, filter_size_required, hash_function_count_required
from spruned.dependencies.pycoinnet.version import version_data_for_peer, NODE_NONE, NODE_WITNESS


def connector_f(host=None, port=None, proxy=None):
    if proxy:
        return aiohttp_socks.open_connection(socks_url=proxy, host=host, port=port)
    return asyncio.open_connection(host=host, port=port)


class P2PConnection(BaseConnection):
    def ping(self, timeout=None):
        self.peer.send_msg('ping', int(time.time()))

    def __init__(
            self, hostname, port, peer=Peer, network=MAINNET, loop=asyncio.get_event_loop(),
            proxy=None, start_score=2,
            is_online_checker: callable=None,
            timeout=3, delayer=async_delayed_task, expire_errors_after=180,
            call_timeout=5, connector=connector_f,
            bloom_filter=None, best_header=None, version_checker=None):

        super().__init__(
            hostname=hostname, proxy=proxy, loop=loop, start_score=start_score,
            is_online_checker=is_online_checker, timeout=timeout, delayer=delayer,
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

    def add_on_blocks_callback(self, callback):
        self._on_block_callbacks.append(callback)

    def add_on_transaction_hash_callback(self, callback):
        self._on_transaction_hash_callbacks.append(callback)

    def add_on_transaction_callback(self, callback):
        self._on_transaction_callbacks.append(callback)

    def add_on_addr_callback(self, callback):
        self._on_addr_callbacks.append(callback)

    @property
    def peer_event_handler(self) -> PeerEvent:
        return self._event_handler

    def add_error(self, *a):
        super().add_error(*a)
        if self.score <= 0:
            self.loop.create_task(self.disconnect())

    def add_success(self):
        self._score += 1

    async def connect(self):
        try:
            async with async_timeout.timeout(self._timeout):
                reader, writer = await self.connector(host=self.hostname, port=self.port, proxy=self.proxy)
                peer = self._peer_factory(
                    reader,
                    writer,
                    self._peer_network.magic_header,
                    self._peer_network.parse_from_data,
                    self._peer_network.pack_from_data
                )
                version_data = version_data_for_peer(
                    peer, version=70015, local_services=NODE_NONE, remote_services=NODE_WITNESS
                )
                peer.version = await peer.perform_handshake(**version_data)
                await self._verify_peer(peer)
                self.starting_height = peer.version['last_block_index']
                if self._bloom_filter:
                    filter_bytes, hash_function_count, tweak = self._bloom_filter.filter_load_params()
                    flags = 0
                    peer.send_msg(
                        "filterload", filter=filter_bytes, hash_function_count=hash_function_count,
                        tweak=tweak, flags=flags
                    )

                self._event_handler = PeerEvent(peer)
                self._version = peer.version

                Logger.p2p.info(
                    'Connected to peer %s:%s (%s)', self.hostname, self.port,
                    self.version and self.version.get('subversion', b'').decode().strip('/')
                )
                Logger.p2p.debug('Peer raw response %s', self.version)
                self.peer = peer
                self.connected_at = int(time.time())
                self._setup_events_handler()
        except Exception as e:
            self.peer = None
            self.failed = True
            Logger.p2p.debug('Exception connecting to %s (%s)', self.hostname, str(e))
            self.loop.create_task(self.on_error('connect'))
            return

        self.loop.create_task(self.on_connect())
        return self

    async def _verify_peer(self, peer):
        if self.best_header and self.best_header['block_height'] - peer.version['last_block_index'] > 5:
            await self.disconnect()
            raise exceptions.PeerVersionMismatchException
        if self.version_checker and not self.version_checker(peer.version):
            await self.disconnect()
            raise exceptions.PeerBlockchainBehindException

    async def on_connect(self):
        for callback in self._on_connect_callbacks:
            self.loop.create_task(callback(self))

    async def disconnect(self):
        try:
            self.peer and self.peer.close()
        except:
            Logger.p2p.error('Error closing with peer: %s', self.peer.peername())
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

    def _on_tx_inv(self, event_handler, name, data):
        for callback in self._on_transaction_callbacks:
            self.loop.create_task(callback(self, data))

    def _on_inv(self, event_handler, name, data):
        try:
            self.loop.create_task(self._process_inv(event_handler, name, data))
        except:
            Logger.p2p.exception('Exception on inv')

    def _on_alert(self, event_handler, name, data):  # pragma: no cover
        try:
            Logger.p2p.debug('Handle alert: %s, %s, %s', event_handler, name, data)
        except:
            Logger.p2p.exception('Exception on alert')

    def _on_addr(self, event_handler, name, data):  # pragma: no cover
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

    def _on_ping(self, event_handler, name, data):
        try:
            self.peer.send_msg("pong", nonce=data["nonce"])
            Logger.p2p.debug('Handle ping: %s, %s, %s', event_handler, name, data)
        except:
            Logger.p2p.exception('Exception on ping')

    async def _process_inv(self, event_handler, name, data):
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
            peers=list(),
            network_checker=check_internet_connection,
            delayer=async_delayed_task,
            loop=asyncio.get_event_loop(),
            proxy=False,
            connections=3,
            sleep_no_internet=30,
            batcher=InvBatcher,
            network=MAINNET,
            batcher_timeout=20,
            ipv6=False,
            servers_storage=save_p2p_peers,
            context=None,
            enable_mempool=False
    ):
        super().__init__(
            peers=peers, network_checker=network_checker, delayer=delayer, ipv6=ipv6,
            loop=loop, proxy=proxy, connections=connections, sleep_no_internet=sleep_no_internet
        )

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

        not enable_mempool and self._create_bloom_filter()  # Mount a dummy filter to avoid receiving tx data

    @property
    def proxy(self):
        return self._proxy

    async def set_best_header(self, value):
        self.best_header = value

    def _create_bloom_filter(self):
        element_count = 1
        false_positive_probability = 0.00000000001
        filter_size = filter_size_required(element_count, false_positive_probability)
        hash_function_count = hash_function_count_required(filter_size, element_count)
        self._pool_filter = BloomFilter(filter_size, hash_function_count=hash_function_count, tweak=1)
        self._pool_filter.add_address('1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa')

    def version_checker(self, peer_version):
        return peer_version['version'] >= self.context.get_network()['min_bitcoin_protocol_version']

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
            await asyncio.sleep(5)

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
            missings = self._required_connections - len(self.established_connections)
            if missings > 0:
                peers = self._pick_multiple_peers(missings)
                for peer in peers:
                    host, port = peer
                    self.loop.create_task(self._connect_peer(host, port))
            elif len(self.established_connections) > self._required_connections:
                Logger.p2p.warning('Too many connections')
                connection = self._pick_connection()
                self.loop.create_task(connection.disconnect())
            #Logger.p2p.debug(
            #    'P2PConnectionPool: Sleeping %ss, connected to %s peers', 10, len(self.established_connections)
            #)
            for connection in self._connections:
                if connection.score <= 0:
                    self.loop.create_task(self._disconnect_peer(connection))
            await asyncio.sleep(10)

    async def _disconnect_peer(self, peer):
        await peer.disconnect()

    async def _connect_peer(self, host: str, port: int):
        Logger.p2p.debug('Allocating peer %s:%s', host, port)
        connection = P2PConnection(
            host, port, loop=self.loop, network=self._network,
            bloom_filter=self._pool_filter, best_header=self.best_header,
            version_checker=self.version_checker, proxy=self._proxy
        )
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
        batcher = self._batcher_factory()
        connections = []
        s = time.time()
        Logger.p2p.debug('Fetching InvItem %s', inv_item)
        future = None
        try:
            async with async_timeout.timeout(timeout if timeout is not None else self._batcher_timeout):
                connections = privileged and self._pick_privileged_connections(peers if peers is not None else 2) or []
                connections = connections or self._pick_multiple_connections(peers if peers is not None else 2)
                for connection in connections:
                    Logger.p2p.debug('Adding connection %s to batcher', connection.hostname)
                    await batcher.add_peer(connection.peer_event_handler)
                future = await batcher.inv_item_to_future(inv_item)
                response = await future
                Logger.p2p.debug('InvItem %s fetched in %ss', inv_item, round(time.time() - s, 4))
                for connection in connections:
                    connection.add_success()
                return response and response
        except asyncio.TimeoutError as error:
            for connection in connections:
                connection.add_error()
            Logger.p2p.debug(
                'Error in get InvItem %s, error: %s, failed in %ss from peers %s',
                inv_item, str(error), round(time.time() - s, 4),
                ', '.join(['{} ({})'.format(x.hostname, len(x.errors)) for x in connections])
            )
            future and future.cancel()
        finally:
            try:
                _ = [self._busy_peers.remove(connection.hostname) for connection in connections]
                del connections
            except KeyError as e:
                Logger.p2p.debug('Peer %s already removed from busy peers', str(e))

            def del_batcher(_b):
                try:
                    _b.stop()
                    del _b._inv_item_future_queue
                    del _b._inv_item_hash_to_future[str(inv_item)]
                except:
                    del _b

            self.loop.run_in_executor(None, lambda: del_batcher(batcher))

    async def on_peer_connected(self, peer):
        Logger.p2p.debug('on_peer_connected: %s', peer.hostname)
        await peer.getaddr()

    async def save_peers(self, data):
        await self._storage_lock.acquire()
        try:
            self._peers = self.servers_storage(data)
        finally:
            self._storage_lock.release()

    async def get_from_connection(self, connection, inv_item):
        batcher = self._batcher_factory()
        await batcher.add_peer(connection.peer_event_handler)
        future = None
        try:
            future = await batcher.inv_item_to_future(inv_item)
            response = await future
            return response
        finally:
            future and future.cancel()
