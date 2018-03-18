import abc
import asyncio
import random

import time

from spruned.application.logging_factory import Logger
from spruned.application.tools import check_internet_connection, async_delayed_task
from spruned.daemon import exceptions
from spruned.daemon.abstracts import ConnectionPoolAbstract, ConnectionAbstract


class BaseConnectionPool(ConnectionPoolAbstract, metaclass=abc.ABCMeta):
    def __init__(self,
                 peers=list(),
                 network_checker=check_internet_connection,
                 delayer=async_delayed_task,
                 loop=asyncio.get_event_loop(),
                 use_tor=False,
                 connections=3,
                 sleep_no_internet=30
                 ):
        self._connections = []
        self._peers = peers
        self._headers_observers = []
        self._new_peers_observers = []
        self._on_connect_observers = []
        self._required_connections = connections
        self._network_checker = network_checker
        self._use_tor = use_tor
        self.loop = loop
        self.delayer = delayer
        self._connection_notified = False
        self._is_online = False
        self._sleep_on_no_internet_connectivity = sleep_no_internet
        self._keepalive = True

    @property
    def peers(self):
        return self._peers

    @property
    def connections(self):
        self._connections = [
            c for c in self._connections if (c.connected or (not c.connected and c.score < c.start_score))
        ]
        return self._connections

    @property
    def established_connections(self):
        return [connection for connection in self.connections if connection.connected]

    def _pick_peer(self):
        i = 0
        while 1:
            if self.peers:
                server = random.choice(self.peers)
                if server not in [connection.hostname for connection in self.connections]:
                    return server
                i += 1
                if i < 100:
                    continue
            raise exceptions.NoServersException

    def _pick_multiple_peers(self, howmany: int):
        assert howmany >= 1
        i = 0
        servers = []
        while 1:
            if self.peers:
                server = self._pick_peer()
                if server in servers:
                    continue
                servers.append(server)
                if len(servers) == howmany:
                    return servers
                if i < 100:
                    continue
            raise exceptions.NoServersException

    def _pick_connection(self, fail_silent=False):
        i = 0
        while 1:
            if self.established_connections:
                connection = random.choice(self.established_connections)
                if connection.connected and connection.score > 0:
                    return connection
                i += 1
                if i < 100:
                    continue
            if not fail_silent:
                raise exceptions.NoPeersException
            return

    def _pick_multiple_connections(self, howmany: int):
        assert howmany >= 1
        i = 0
        connections = []
        while 1:
            if self.established_connections:
                connection = self._pick_connection()
                if connection in connections:
                    i += 1
                    if i > 100:
                        raise exceptions.NoPeersException
                    continue
                connections.append(connection)
                if len(connections) == howmany:
                    return connections
            i += 1
            if i < 100:
                continue
            raise exceptions.NoPeersException

    def is_online(self):
        return self._is_online

    def add_on_connected_observer(self, observer):
        self._on_connect_observers.append(observer)

    def add_header_observer(self, observer):
        self._headers_observers.append(observer)

    async def on_peer_connected(self, peer: ConnectionAbstract):
        future = peer.subscribe(
            'blockchain.headers.subscribe',
            self.on_peer_received_header,
            self.on_peer_received_header
        )
        self.loop.create_task(self.delayer(future))

    def on_peer_disconnected(self, peer: ConnectionAbstract):
        peer.add_error(int(time.time()) + 180)

    async def on_peer_received_header(self, peer: ConnectionAbstract):
        for observer in self._headers_observers:
            self.loop.create_task(self.delayer(observer(peer, peer.last_header)))

    async def on_peer_received_peers(self, peer: ConnectionAbstract):
        raise NotImplementedError

    async def on_peer_error(self, peer: ConnectionAbstract, error_type=None):
        if error_type == 'connect':
            if await self._check_internet_connectivity():
                peer.add_error(int(time.time()) + 180)
            return
        if self.is_online:
            Logger.electrum.debug('Peer %s error', peer)
            await self._handle_peer_error(peer)

    def stop(self):
        self._keepalive = False

    async def _check_internet_connectivity(self):
        if self._network_checker is None:  # pragma: no cover
            self._is_online = True
            return
        self._is_online = self._network_checker()
        return self._is_online

    async def _handle_peer_error(self, peer: ConnectionAbstract):
        Logger.electrum.debug('Handling connection error for %s', peer.hostname)
        if not peer.connected:
            peer.add_error()
            return
        if not peer.score:
            Logger.electrum.error('Disconnecting from peer %s, score: %s', peer.hostname, peer.score)
            self.loop.create_task(self.delayer(peer.disconnect()))
            return
        if not await peer.ping(timeout=2):
            Logger.electrum.error('Ping timeout from peer %s, score: %s', peer.hostname, peer.score)
            self.loop.create_task(self.delayer(peer.disconnect()))

    def connect(self):
        raise NotImplementedError
