import asyncio
import random

import async_timeout
from pycoin.message.InvItem import InvItem
from pycoinnet.Peer import Peer
from pycoinnet.PeerEvent import PeerEvent
from pycoinnet.networks import MAINNET
from pycoinnet.inv_batcher import InvBatcher
from pycoinnet.version import version_data_for_peer
from spruned.application.logging_factory import Logger
from spruned.daemon.p2p.utils import dns_bootstrap_servers


class P2PConnection:
    def __init__(self, host, port, peer=Peer, network=MAINNET, loop=asyncio.get_event_loop()):
        self.host = host
        self.port = port
        self._peer_factory = peer
        self._peer_network = network
        self.peer: peer = None
        self._version = None
        self._reader = None
        self._writer = None
        self.loop = loop

    @property
    def connected(self):
        return bool(self.peer)

    async def connect(self):
        self._reader, self._writer = await asyncio.open_connection(host=self.host, port=self.port)
        peer = Peer(
            self._reader,
            self._writer,
            self._peer_network.magic_header,
            self._peer_network.parse_from_data,
            self._peer_network.pack_from_data
        )
        version_data = version_data_for_peer(peer)
        peer.version = await peer.perform_handshake(**version_data)
        self._version = peer.version
        self.peer = peer
        return self

    async def disconnect(self):
        try:
            self.peer and self.peer.close()
        except:
            Logger.p2p.error('Error closing with peer: %s', self.peer.peername())
        self.peer = None


class P2PConnectionPool:
    def __init__(
            self, inv_batcher=InvBatcher, network=MAINNET, connections=1,
            loop=asyncio.get_event_loop(), peer_event_factory=PeerEvent,
            network_checker=None, peers_factory=dns_bootstrap_servers
    ):
        self._connections = []
        self._peers = []
        self._batcher_factory = inv_batcher
        self._network = network
        self._required_connections = connections
        self.loop = loop
        self._peer_event_handler_factory = peer_event_factory
        self._peers_factory = peers_factory
        self._network_checker = network_checker

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
            peer_event_handler = self._peer_event_handler_factory(connection.peer)
            await batcher.add_peer(peer_event_handler)
        return batcher

    async def bootstrap_peers(self):
        with async_timeout.timeout(10):
            self._peers = await self._peers_factory(self._network)

    async def connect(self):
        while not self._peers:
            self.loop.create_task(self.bootstrap_peers())
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
        await connection.connect()
        if connection.connected:
            self._connections.append(connection)
        else:
            Logger.p2p.warning('Connection to %s - %s failed', host, port)

    def _pick_peer(self):
        if not self._peers:
            return
        return random.choice(self._peers)

    def _pick_connection(self):
        if not self._connections:
            return
        return random.choice(self.connections)

    async def get(self, inv_item: InvItem):
        batcher = await self._get_batcher()
        future = await batcher.inv_item_to_future(inv_item)
        response = await future
        return response and response
