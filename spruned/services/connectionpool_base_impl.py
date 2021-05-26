import abc
import asyncio
import random
import time
from typing import List

import typing

from spruned.application.logging_factory import Logger
from spruned.application.tools import check_internet_connection, async_delayed_task
from spruned.services import exceptions
from spruned.services.abstracts import ConnectionPoolAbstract, ConnectionAbstract


class BaseConnectionPool(ConnectionPoolAbstract, metaclass=abc.ABCMeta):
    def __init__(
            self,
            peers=None,
            network_checker=check_internet_connection,
            delayer=async_delayed_task,
            loop=asyncio.get_event_loop(),
            proxy=False,
            connections=3,
            sleep_no_internet=30,
            ipv6=False
    ):
        self.connectionpicker_lock = asyncio.Lock()
        self.delayer = delayer
        self.loop = loop
        self.starting_height = None
        self._connections = []

        self._peers: typing.Set = peers or set()
        self._banned_peers: typing.Dict = dict()
        self._used_peers: typing.Set = set()
        self._headers_observers = []
        self._new_peers_observers = []
        self._on_connect_observers = []
        self._required_connections = connections
        self._network_checker = network_checker
        self._proxy = proxy
        self._connection_notified = False
        self._is_online = False
        self._sleep_on_no_internet_connectivity = sleep_no_internet
        self._keepalive = True
        self._ipv6 = ipv6
        self._ban_time = 60

    def _expire_peer_bans(self):
        now = int(time.time())
        for peer, ban_timestamp in list(self._banned_peers.items()):
            if now - ban_timestamp > self._ban_time:
                self._banned_peers.pop(peer)
                self._peers.add(peer)

    @property
    def peers(self):
        return self._peers

    def _get_peer(self):
        peers = self._peers - set(self._banned_peers) - self._used_peers
        if not peers:
            raise exceptions.NoPeersException
        peer = peers.pop()
        self._peers.remove(peer)
        self._used_peers.add(peer)
        return peer

    def ban_peer(self, peer):
        self._used_peers.remove(peer)
        self._banned_peers[peer] = int(time.time())

    def _get_multiple_peers(self, count: int):
        return list(
            map(
                self._get_peer(),
                range(0, count)
            )
        )

    def cleanup_connections(self):
        self._connections = self.connections

    @property
    def connections(self):
        return list(filter(lambda c: not c.failed or c.score > 0, self._connections))

    @property
    def established_connections(self):
        return list(filter(lambda c: c.connected, self.connections))

    @property
    def free_connections(self):
        return list(filter(lambda c: c.score > 0 and c.connected, self.connections))

    def get_connection(self):
        if not self.free_connections:
            raise exceptions.NoConnectionsAvailableException()
        connection = random.choice(self.free_connections)
        return connection

    async def get_multiple_connections(self, count: int) -> List:
        try:
            await self.connectionpicker_lock.acquire()
            connections = list(
                map(
                    lambda _: self.get_connection(),
                    range(0, count)
                )
            )
            if len(connections) < count:
                raise exceptions.NoPeersException
            return connections
        finally:
            self.connectionpicker_lock.release()

    def is_online(self):
        return self._is_online

    def add_on_connected_observer(self, observer: callable):
        self._on_connect_observers.append(observer)

    def add_header_observer(self, observer: callable):
        self._headers_observers.append(observer)

    def on_peer_disconnected(self, peer: ConnectionAbstract, *_):
        peer.add_error(int(time.time()), origin='on_peer_disconnected') # ?!

    async def on_peer_received_header(self, peer: ConnectionAbstract, *_):
        for observer in self._headers_observers:
            self.loop.create_task(observer(peer, peer.last_header))

    async def on_peer_received_peers(self, peer: ConnectionAbstract, *_):
        raise NotImplementedError

    async def on_peer_error(self, connection: ConnectionAbstract, error_type: bool = None):
        if error_type == 'connect':
            if await self._check_internet_connectivity():
                await connection.disconnect()
            return
        if self.is_online:
            Logger.root.debug('Connection %s error', connection)
            await self._handle_connection_error(connection)

    def stop(self):
        self._keepalive = False

    async def _check_internet_connectivity(self):
        if self._network_checker is None:  # pragma: no cover
            self._is_online = True
            return
        self._is_online = await self._network_checker()
        return self._is_online

    async def _handle_connection_error(self, connection: ConnectionAbstract):
        Logger.root.debug('Handling connection error for %s', connection.hostname)
        if not connection.connected:
            connection.add_error(origin='handle_peer_error')
            return
        if not connection.score:
            Logger.root.error('Disconnecting from peer %s, score: %s', connection.hostname, connection.score)
            self.loop.create_task(self.delayer(connection.disconnect()))
            return
        if not await connection.ping(timeout=2):
            Logger.root.error('Ping timeout from peer %s, score: %s', connection.hostname, connection.score)
            self.loop.create_task(self.delayer(connection.disconnect()))

    def connect(self):
        raise NotImplementedError
