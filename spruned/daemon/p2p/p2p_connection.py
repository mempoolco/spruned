import asyncio

import async_timeout
from pycoin.message.InvItem import InvItem, ITEM_TYPE_TX, ITEM_TYPE_BLOCK, ITEM_TYPE_MERKLEBLOCK
from pycoinnet.Peer import Peer
from pycoinnet.PeerEvent import PeerEvent
from pycoinnet.networks import MAINNET
from pycoinnet.inv_batcher import InvBatcher
from pycoinnet.version import version_data_for_peer
from spruned.application.logging_factory import Logger
from spruned.application.tools import check_internet_connection, async_delayed_task
from spruned.daemon.abstracts import ConnectionAbstract
from spruned.daemon.connectionpool_base_impl import BaseConnectionPool


class P2PConnection(ConnectionAbstract):
    @property
    def start_score(self):
        raise NotImplementedError

    @property
    def hostname(self):
        raise NotImplementedError

    @property
    def score(self):
        raise NotImplementedError

    @property
    def version(self):
        raise NotImplementedError

    @property
    def last_header(self):
        raise NotImplementedError

    def is_online(self) -> bool:
        raise NotImplementedError

    def ping(self, timeout=None):
        raise NotImplementedError

    @property
    def errors(self):
        raise NotImplementedError

    def subscribe(self, channel, on_subscription, on_traffic):
        raise NotImplementedError

    def add_error(self, *a):
        raise NotImplementedError

    def __init__(
            self, host, port, peer=Peer, network=MAINNET, loop=asyncio.get_event_loop(),
            peer_event_factory=PeerEvent):
        self.hostname = host
        self.port = port
        self._peer_factory = peer
        self._peer_network = network
        self.peer: peer = None
        self._version = None
        self._reader = None
        self._writer = None
        self.loop = loop
        self._peer_event_factory = peer_event_factory
        self._event_handler = None
        self._on_headers_callbacks = []
        self._on_connect_callbacks = []
        self._on_disconnect_callbacks = []
        self._on_peers_callbacks = []
        self._on_errors_callbacks = []
        self._on_block_callbacks = []
        self._on_transaction_callbacks = []

    def add_on_header_callbacks(self, callback):
        self._on_headers_callbacks.append(callback)

    def add_on_connect_callback(self, callback):
        self._on_connect_callbacks.append(callback)

    def add_on_disconnect_callback(self, callback):
        self._on_disconnect_callbacks.append(callback)

    def add_on_peers_callback(self, callback):
        self._on_peers_callbacks.append(callback)

    def add_on_error_callback(self, callback):
        self._on_errors_callbacks.append(callback)

    def add_on_block_callbacks(self, callback):
        self._on_block_callbacks.append(callback)

    def add_on_transaction_callback(self, callback):
        self._on_transaction_callbacks.append(callback)

    @property
    def peer_event_handler(self) -> PeerEvent:
        return self._event_handler

    @property
    def connected(self):
        return bool(self.peer)

    async def connect(self):
        try:
            with async_timeout.timeout(self._timeout):
                self._reader, self._writer = await asyncio.open_connection(host=self.hostname, port=self.port)
                peer = Peer(
                    self._reader,
                    self._writer,
                    self._peer_network.magic_header,
                    self._peer_network.parse_from_data,
                    self._peer_network.pack_from_data
                )
                version_data = version_data_for_peer(peer)
                peer.version = await peer.perform_handshake(**version_data)
        except Exception as e:
            Logger.p2p.error('Exception connecting to %s (%s)', self.hostname, e)
            await self.on_error('connect')
            return

        self._version = peer.version
        self.peer = peer
        self._event_handler = self._peer_event_factory(self.peer)
        await self.on_connect()
        self._setup_events_handler()

    async def on_connect(self):
        for callback in self._on_connect_callbacks:
            self.loop.create_task(callback(self))

    async def disconnect(self):
        try:
            self.peer and self.peer.close()
        except:
            Logger.p2p.error('Error closing with peer: %s', self.peer.peername())
        self.peer = None

    def _setup_events_handler(self):
        self.peer_event_handler.set_request_callback('inv', self._on_inv)
        self.peer_event_handler.set_request_callback('addr', self._on_addr)
        self.peer_event_handler.set_request_callback('alert', self._on_alert)
        self.peer_event_handler.set_request_callback('ping', self._on_ping)

    def _on_inv(self, event_handler, name, data):
        self.loop.create_task(self._process_inv(event_handler, name, data))

    def _on_alert(self, event_handler, name, data):
        Logger.p2p.debug('Handle alert: %s, %s, %s', event_handler, name, data)

    def _on_addr(self, event_handler, name, data):
        Logger.p2p.debug('Handle addr: %s, %s, %s', event_handler, name, data)
        for callback in self._on_peers_callbacks:
            self.loop.create_task(callback(self, data))

    def _on_ping(self, event_handler, name, data):
        self.peer.send_msg("pong", nonce=data["nonce"])

    async def _process_inv(self, event_handler, name, data):
        for item in data.get('items'):
            if item.item_type == ITEM_TYPE_TX:
                False and Logger.p2p.debug('Received new transaction: %s', item.data)
                for callback in self._on_transaction_callbacks:
                    item: InvItem
                    self.loop.create_task(callback(self, item))
            elif item.item_type == ITEM_TYPE_BLOCK:
                Logger.p2p.debug('Received new block: %s', item.data)
                for callback in self._on_block_callbacks:
                    self.loop.create_task(callback(self, item))
            elif item.item_type == ITEM_TYPE_MERKLEBLOCK:
                Logger.p2p.debug('Received new header: %s', item.data)
                for callback in self._on_headers_callbacks:
                    self.loop.create_task(callback(self, item))
            else:
                Logger.p2p.error('Error InvType: %s, %s, %s', event_handler, name, item)


class P2PConnectionPool(BaseConnectionPool):
    def on_peer_received_peers(self, peer: ConnectionAbstract):
        raise NotImplementedError

    def __init__(
            self,
            peers=list(),
            network_checker=check_internet_connection,
            delayer=async_delayed_task,
            loop=asyncio.get_event_loop(),
            use_tor=False,
            connections=3,
            sleep_no_internet=30,
            inv_batcher=InvBatcher,
            network=MAINNET,
    ):
        super().__init__(
            peers=peers, network_checker=network_checker, delayer=delayer,
            loop=loop, use_tor=use_tor, connections=connections, sleep_no_internet=sleep_no_internet
        )
        self._batcher_factory = inv_batcher
        self._network = network

    @property
    def available(self):
        return len(self.connections) >= self._required_connections

    def add_peer(self, peer):
        self._peers.append(peer)

    @property
    def connections(self):
        return self._connections

    async def _get_batcher(self) -> InvBatcher:
        batcher = self._batcher_factory()
        for connection in self.connections:
            peer_event_handler = connection.peer_event_handler
            await batcher.add_peer(peer_event_handler)
        return batcher

    async def connect(self):
        while not self._peers:
            await asyncio.sleep(5)

        while 1:
            missings = len(self.connections) < self._required_connections
            if missings:
                host, port = self._pick_peer()
                self.loop.create_task(self._connect_peer(host, port))
            elif len(self.connections) > self._required_connections:
                Logger.p2p.warning('Too many connections')
                connection = self._pick_connection()
                self.loop.create_task(connection.disconnect())
            s = missings and 2 or 10
            Logger.p2p.debug('P2PConnectionPool: Sleeping for %s', s)
            await asyncio.sleep(s)

    async def _connect_peer(self, host: str, port: int):
        connection = P2PConnection(host, port, loop=self.loop, network=self._network)
        try:
            await connection.connect()
        except (asyncio.CancelledError, OSError) as error:
            Logger.p2p.error('Error connecting to %s - %s, error: %s', host, port, error)
        if connection.connected:
            self._connections.append(connection)
            connection.add_on_connect_callback(self.on_peer_connected)
            connection.add_on_header_callbacks(self.on_peer_received_header)
            connection.add_on_peers_callback(self.on_peer_received_peers)
            connection.add_on_error_callback(self.on_peer_error)
        else:
            Logger.p2p.warning('Connection to %s - %s failed', host, port)

    async def get(self, inv_item: InvItem):
        batcher = await self._get_batcher()
        future = await batcher.inv_item_to_future(inv_item)
        response = await future
        return response and response
