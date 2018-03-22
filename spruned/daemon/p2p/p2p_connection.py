import asyncio
import async_timeout
from pycoin.message.InvItem import InvItem, ITEM_TYPE_TX
from pycoinnet.Peer import Peer
from pycoinnet.PeerEvent import PeerEvent
from pycoinnet.networks import MAINNET
from pycoinnet.inv_batcher import InvBatcher
from pycoinnet.version import version_data_for_peer, NODE_BLOOM
from spruned.application.logging_factory import Logger
from spruned.application.tools import check_internet_connection, async_delayed_task
from spruned.daemon.connection_base_impl import BaseConnection
from spruned.daemon.connectionpool_base_impl import BaseConnectionPool


class P2PConnection(BaseConnection):
    def ping(self, timeout=None):
        return True  # TODO

    def __init__(
            self, hostname, port, peer=Peer, network=MAINNET, loop=asyncio.get_event_loop(),
            use_tor=None, start_score=10,
            is_online_checker: callable=None,
            timeout=10, delayer=async_delayed_task, expire_errors_after=180,
            call_timeout=30):

        super().__init__(
            hostname=hostname, use_tor=use_tor, loop=loop, start_score=start_score,
            is_online_checker=is_online_checker, timeout=timeout, delayer=delayer,
            expire_errors_after=expire_errors_after
        )
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

    @property
    def connected(self):
        return bool(self.peer)

    def add_on_block_callbacks(self, callback):
        self._on_block_callbacks.append(callback)

    def add_on_transaction_callback(self, callback):
        self._on_transaction_callbacks.append(callback)

    @property
    def peer_event_handler(self) -> PeerEvent:
        return self._event_handler

    async def connect(self):
        try:
            async with async_timeout.timeout(self._timeout):
                reader, writer = await asyncio.open_connection(host=self.hostname, port=self.port)
                peer = Peer(
                    reader,
                    writer,
                    self._peer_network.magic_header,
                    self._peer_network.parse_from_data,
                    self._peer_network.pack_from_data
                )
                version_data = version_data_for_peer(peer, version=70011, local_services=NODE_BLOOM)
                peer.version = await peer.perform_handshake(**version_data)
                self._event_handler = PeerEvent(peer)
                self._version = peer.version
                self.peer = peer
                self._setup_events_handler()
        except Exception as e:
            Logger.p2p.error('Exception connecting to %s (%s)', self.hostname, e)
            self.loop.create_task(self.on_error('connect'))
            return

        self.loop.create_task(self.on_connect())
        return self

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

    def _setup_events_handler(self):
        self.peer_event_handler.set_request_callback('inv', self._on_inv)
        self.peer_event_handler.set_request_callback('addr', self._on_addr)
        self.peer_event_handler.set_request_callback('alert', self._on_alert)
        self.peer_event_handler.set_request_callback('ping', self._on_ping)

    def _on_inv(self, event_handler, name, data):
        try:
            self.loop.create_task(self._process_inv(event_handler, name, data))
        except:
            Logger.p2p.exception('Exception on inv')

    def _on_alert(self, event_handler, name, data):
        try:
            Logger.p2p.debug('Handle alert: %s, %s, %s', event_handler, name, data)
        except:
            Logger.p2p.exception('Exception on alert')

    def _on_addr(self, event_handler, name, data):
        try:
            Logger.p2p.debug('Handle addr: %s, %s, %s', event_handler, name, data)
            for callback in self._on_peers_callbacks:
                self.loop.create_task(callback(self, data))
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
                for callback in self._on_transaction_callbacks:
                    item: InvItem
                    self.loop.create_task(callback(self, item))
            else:
                Logger.p2p.error('Unhandled InvType: %s, %s, %s', event_handler, name, item)
        Logger.p2p.debug('Received %s items, txs: %s', len(data.get('items')), txs)


class P2PConnectionPool(BaseConnectionPool):
    async def on_peer_received_peers(self, peer, *a):
        Logger.p2p.debug('Received peers from peer: %s: (%s)', peer.hostname, a)

    def __init__(
            self,
            peers=list(),
            network_checker=check_internet_connection,
            delayer=async_delayed_task,
            loop=asyncio.get_event_loop(),
            use_tor=False,
            connections=3,
            sleep_no_internet=30,
            batcher=InvBatcher,
            network=MAINNET,
            batcher_timeout=20
    ):
        super().__init__(
            peers=peers, network_checker=network_checker, delayer=delayer,
            loop=loop, use_tor=use_tor, connections=connections, sleep_no_internet=sleep_no_internet
        )
        self._batcher_factory = batcher
        self._network = network
        self._batcher_timeout = batcher_timeout
        self._batcher = self._batcher_factory(target_batch_time=self._batcher_timeout-1)

    @property
    def available(self):
        return len(self.connections) >= self._required_connections

    def add_peer(self, peer):
        self._peers.append(peer)

    @property
    def connections(self):
        return self._connections

    async def connect(self):
        await self._check_internet_connectivity()
        self._keepalive = True
        while not self._peers:
            Logger.p2p.warning('Peers not loaded. Sleeping.')
            await asyncio.sleep(5)

        while self._keepalive:
            if not self.is_online():
                Logger.electrum.error(
                    'Looks like there is no internet connection available. '
                    'Sleeping the connection loop for %s',
                    self._sleep_on_no_internet_connectivity
                )
                await asyncio.sleep(self._sleep_on_no_internet_connectivity)
                await self._check_internet_connectivity()
                continue

            missings = len(self.established_connections) < self._required_connections
            if missings:
                host, port = self._pick_peer()
                self.loop.create_task(self._connect_peer(host, port))
                await asyncio.sleep(1)
            elif len(self.established_connections) > self._required_connections:
                Logger.p2p.warning('Too many connections')
                connection = self._pick_connection()
                self.loop.create_task(connection.disconnect())
            s = missings and 0.1 or 10
            Logger.p2p.debug('P2PConnectionPool: Sleeping %ss', s)
            await asyncio.sleep(s)

    async def _connect_peer(self, host: str, port: int):
        Logger.p2p.debug('Allocating peer %s:%s', host, port)
        connection = P2PConnection(host, port, loop=self.loop, network=self._network)
        if not await connection.connect():
            Logger.p2p.warning('Connection to %s - %s failed', host, port)
            return
        self._connections.append(connection)
        connection.add_on_connect_callback(self.on_peer_connected)
        connection.add_on_header_callbacks(self.on_peer_received_header)
        connection.add_on_peers_callback(self.on_peer_received_peers)
        connection.add_on_error_callback(self.on_peer_error)
        await self._batcher.add_peer(connection.peer_event_handler)

    async def get(self, inv_item: InvItem):
        peers = []
        try:
            async with async_timeout.timeout(self._batcher_timeout):
                future = await self._batcher.inv_item_to_future(inv_item)
                response = await future
                return response and response
        except Exception as error:
            Logger.p2p.error('Error in get %s, error: %s', inv_item, error)
            for peer in peers:
                self.loop.create_task(peer.disconnect())

    async def on_peer_connected(self, peer):
        Logger.p2p.debug('on_peer_connected: %s', peer.hostname)
