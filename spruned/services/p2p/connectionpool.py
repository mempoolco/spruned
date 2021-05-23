import asyncio
import aiohttp_socks
import typing

from spruned.application.logging_factory import Logger
from spruned.application.tools import check_internet_connection, async_delayed_task
from spruned.services import exceptions
from spruned.services.p2p import save_p2p_peers
from spruned.services.connectionpool_base_impl import BaseConnectionPool
from spruned.services.p2p.connection import P2PConnection
from spruned.dependencies.pycoinnet.networks import MAINNET
from spruned.dependencies.pycoinnet.pycoin.bloom import BloomFilter, filter_size_required, \
    hash_function_count_required


def connector_f(host: str = None, port: int = None, proxy: str = None):
    if proxy:
        return aiohttp_socks.open_connection(socks_url=proxy, host=host, port=port)
    return asyncio.open_connection(host=host, port=port)


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
            connections=1,
            network=MAINNET,
            ipv6=False,
            servers_storage=save_p2p_peers,
            context=None,
            enable_mempool=False,
            max_peers_per_request=4
    ):
        super().__init__(
            peers=peers or [],
            network_checker=network_checker,
            delayer=delayer,
            ipv6=ipv6,
            loop=loop,
            proxy=proxy,
            connections=connections,
            sleep_no_internet=30
        )
        self.max_peers_per_request = max_peers_per_request
        self._pool_filter = None
        self._network = network
        self.servers_storage = servers_storage
        self._storage_lock = asyncio.Lock()
        self._pool_size = connections
        self._local_header = None
        self._on_transactions_hash_callbacks = []
        self._on_transactions_callbacks = []
        self._on_blocks_callbacks = []
        self._on_headers_callbacks = []
        self.context = context
        self.enable_mempool = enable_mempool
        self._create_bloom_filter()

    @property
    def proxy(self):
        return self._proxy

    async def set_local_current_header(self, value: typing.Dict):
        self._local_header = value

    def _create_bloom_filter(self):
        element_count = 1
        false_positive_probability = 0.0001
        filter_size = filter_size_required(element_count, false_positive_probability)
        hash_function_count = hash_function_count_required(filter_size, element_count)
        self._pool_filter = BloomFilter(filter_size, hash_function_count=hash_function_count, tweak=1)
        self._pool_filter.add_item(bytes.fromhex('ff'*16))

    def version_checker(self, peer_version: typing.Dict):
        return self.context.get_network()['evaluate_peer_version'](peer_version)

    @property
    def required_connections(self):
        return self._required_connections

    @property
    def completed(self):
        return len(self.established_connections) >= self._required_connections

    def add_peer(self, peer: typing.Tuple):
        self._peers.add(peer)

    def add_on_transaction_hash_callback(self, callback):
        self._on_transactions_hash_callbacks.append(callback)

    def add_on_transaction_callback(self, callback):
        self._on_transactions_callbacks.append(callback)

    def add_on_block_callback(self, callback):
        self._on_blocks_callbacks.append(callback)

    def add_on_headers_callback(self, callback):
        self._on_headers_callbacks.append(callback)

    @property
    def connections(self):
        return list(
            filter(
                lambda c: not c.failed,
                self._connections
            )
        )

    async def connect(self):
        await self._check_internet_connectivity()
        while 1:
            self._expire_peer_bans()
            if self.completed or not self._keepalive:
                await asyncio.sleep(5)
                continue
            if not self._peers:
                Logger.p2p.debug('No P2P peers loaded')
                await asyncio.sleep(5)
                continue
            if not self.is_online():
                Logger.p2p.error('No internet. Sleeping.')
                await self._check_internet_connectivity()
                await asyncio.sleep(5)
                continue
            try:
                await self._connect()
            except exceptions.NoPeersException:
                Logger.p2p.debug('Keep-Alive: Peers loaded but not available. Waiting.')
                await asyncio.sleep(5)
                continue
            await asyncio.sleep(1)

    async def _connect(self):
        peer = self._get_peer()
        host, port = peer
        await self._connect_to_peer(host, port)

    @staticmethod
    async def _disconnect_peer(connection: P2PConnection):
        await connection.disconnect()

    async def _connect_to_peer(self, host: str, port: int):
        connection = P2PConnection(
            host,
            port,
            loop=self.loop,
            network=self._network,
            bloom_filter=self._pool_filter,
            best_header=self._local_header,
            version_checker=self.version_checker,
            proxy=self._proxy
        )
        connection.pool = self
        self._connections.append(connection)
        connection.add_on_connect_callback(self.on_peer_connected)
        connection.add_on_header_callbacks(self.on_peer_received_header)
        connection.add_on_peers_callback(self.on_peer_received_peers)
        connection.add_on_error_callback(self.on_peer_error)
        connection.add_on_addr_callback(self.save_peers)
        for callback in self._on_transactions_hash_callbacks:
            connection.add_on_transaction_hash_callback(callback)
        for callback in self._on_transactions_callbacks:
            connection.add_on_transaction_callback(callback)
        for callback in self._on_blocks_callbacks:
            connection.add_on_blocks_callback(callback)
        for callback in self._on_headers_callbacks:
            connection.add_on_headers_callback(callback)
        self.loop.create_task(self._handle_connection_connect(connection))

    async def _handle_connection_connect(self, connection: P2PConnection):
        try:
            await connection.connect()
        except:
            self.ban_peer((connection.hostname, connection.port))

    @staticmethod
    async def _clean_connections(connections: typing.List[P2PConnection]):
        for connection in connections:
            await connection.mark_free()

    @staticmethod
    async def on_peer_connected(connection: P2PConnection):
        Logger.p2p.debug('on_peer_connected: %s', connection.hostname)
        await connection.getaddr()

    async def save_peers(self, data):
        await self._storage_lock.acquire()
        try:
            pass
            #self._peers = self.servers_storage(data)
        finally:
            self._storage_lock.release()
