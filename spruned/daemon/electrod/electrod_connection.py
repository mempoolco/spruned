import asyncio
import os
import binascii
import random
import subprocess
import time
from typing import Dict, List
import async_timeout
from connectrum.client import StratumClient
from connectrum.svr_info import ServerInfo

from spruned.application import settings
from spruned.application.logging_factory import Logger
from spruned.application.tools import async_delayed_task, check_internet_connection
from spruned.daemon import exceptions


class ElectrodConnection:
    def __init__(
            self, hostname: str, protocol: str, keepalive=180,
            client=StratumClient, serverinfo=ServerInfo, nickname=None, use_tor=False, loop=None,
            start_score=10, timeout=10, expire_errors_after=180,
            is_online_checker: callable=None, delayer=async_delayed_task
    ):
        self.hostname = hostname
        self.protocol = protocol
        self.keepalive = keepalive
        self.client: StratumClient = client()
        self.serverinfo_factory = serverinfo
        self.client.keepalive_interval = keepalive
        self.nickname = nickname or binascii.hexlify(os.urandom(8)).decode()
        self.use_tor = use_tor
        self._version = None
        self._on_headers_callbacks = []
        self._on_connect_callbacks = []
        self._on_disconnect_callbacks = []
        self._on_errors_callbacks = []
        self._on_peers_callbacks = []
        self.loop = loop or asyncio.get_event_loop()
        self._start_score = start_score
        self._last_header = None
        self._subscriptions = []
        self._timeout = timeout
        self._errors = []
        self._peers = []
        self._expire_errors_after = expire_errors_after
        self._is_online_checker = is_online_checker
        self.delayer = delayer

    def is_online(self):
        if self._is_online_checker is not None:
            return self._is_online_checker()
        return True

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

    async def on_header(self, header):
        self._last_header = header
        for callback in self._on_headers_callbacks:
            self.loop.create_task(callback(self))

    async def on_connect(self):
        for callback in self._on_connect_callbacks:
            self.loop.create_task(callback(self))

    def on_connectrum_disconnect(self, *_, **__):
        for callback in self._on_disconnect_callbacks:
            self.loop.create_task(callback(self))

    async def on_error(self, error):
        if not self.is_online:
            return
        self._errors.append(int(time.time()))
        for callback in self._on_errors_callbacks:
            self.loop.create_task(callback(self, error_type=error))

    async def connect(self):
        try:
            with async_timeout.timeout(self._timeout):
                self._version = await self.client.connect(
                    self.serverinfo_factory(
                        self.nickname, hostname=self.hostname, ports=self.protocol, version='1.2'
                    ),
                    disconnect_callback=self.on_connectrum_disconnect,
                    disable_cert_verify=True,
                    use_tor=self.use_tor
                )
                Logger.electrum.debug('Connected to %s', self.hostname)
                await self.on_connect()
        except Exception as e:
            Logger.electrum.error('Exception connecting to %s (%s)', self.hostname, e)
            await self.on_error('connect')

    @property
    def start_score(self):
        return self._start_score

    @property
    def version(self):
        return self._version

    @property
    def connected(self):
        return bool(self.client.protocol)

    async def ping(self, timeout=2) -> (None, float):
        try:
            async with async_timeout.timeout(timeout):
                now = time.time()
                await self.client.RPC('server.version')
                return time.time() - now
        except asyncio.TimeoutError:
            return

    @property
    def last_header(self) -> Dict:
        return self._last_header

    @property
    def subscriptions(self) -> List:
        return self._subscriptions

    @property
    def score(self):
        return self._start_score - len(self.errors)

    @property
    def errors(self):
        now = int(time.time())
        self._errors = [error for error in self._errors if now - error < self._expire_errors_after]
        return self._errors

    @property
    def peers(self):
        return self._peers

    async def rpc_call(self, method: str, *args):
        try:
            async with async_timeout.timeout(self._timeout):
                return await self.client.RPC(method, *args)
        except Exception as e:
            Logger.electrum.error('exception on rpc call: %s', e)
            self.loop.create_task(self.delayer(self.on_error(e)))

    async def subscribe(self, channel: str, on_subscription: callable, on_traffic: callable):
        try:
            async with async_timeout.timeout(self._timeout):
                future, q = self.client.subscribe(channel)
            self.subscriptions.append({channel: q})
            header = await future
            self._last_header = header
            on_subscription and self.loop.create_task(on_subscription(self))
            self.loop.create_task(self._poll_queue(q, on_traffic))
        except Exception as e:
            Logger.electrum.error('subscribe %s on %s failed', channel, self.hostname)
            self.loop.create_task(self.delayer(self.on_error(e)))

    async def _poll_queue(self, queue: asyncio.Queue, callback):
        try:
            header = await queue.get()
            Logger.electrum.debug('new data from queue: %s', header)
            self._last_header = header[0]
            self.loop.create_task(self.delayer(callback(self)))
            self.loop.create_task(self.delayer(self._poll_queue(queue, callback)))
        except Exception as e:
            Logger.electrum.exception('queue poll failed')
            self.loop.create_task(self.delayer(self.on_error(e)))

    async def disconnect(self):
        try:
            self.client.close()
        except Exception as e:
            Logger.electrum.error('Exception disconnecting from peer: %s', e)
            self.client.protocol = None


class ElectrodConnectionPool:
    def __init__(self,
                 connections=3,
                 loop=asyncio.get_event_loop(),
                 use_tor=False,
                 electrum_servers=[],
                 network_checker=check_internet_connection,
                 delayer=async_delayed_task,
                 connection_factory=ElectrodConnection,
                 sleep_no_internet=30
                 ):
        self._use_tor = use_tor
        self._servers = electrum_servers
        self._connections = []
        self._required_connections = connections
        self._keepalive = True
        self.loop = loop
        self._connections_keepalive_time = 120
        self._headers_observers = []
        self._new_peers_observers = []
        self._on_connect_observers = []
        self._connection_notified = False
        self._is_online = False
        self.delayer = delayer
        self._network_checker = network_checker
        self._connection_factory = connection_factory
        self._sleep_on_no_internet_connectivity = sleep_no_internet

    def is_online(self):
        return self._is_online

    def add_on_connected_observer(self, observer):
        self._on_connect_observers.append(observer)

    def add_header_observer(self, observer):
        self._headers_observers.append(observer)

    async def on_peer_connected(self, peer: ElectrodConnection):
        future = peer.subscribe(
            'blockchain.headers.subscribe',
            self.on_peer_received_header,
            self.on_peer_received_header
        )
        self.loop.create_task(self.delayer(future))

    def on_peer_disconnected(self, peer: ElectrodConnection):
        pass

    async def on_peer_received_header(self, peer: ElectrodConnection):
        for observer in self._headers_observers:
            self.loop.create_task(self.delayer(observer(peer, peer.last_header)))

    async def on_peer_received_peers(self, peer: ElectrodConnection):
        for observer in self._new_peers_observers:
            self.loop.create_task(self.delayer(observer(peer.peers)))

    async def on_peer_error(self, peer: ElectrodConnection, error_type=None):
        if error_type == 'connect':
            await self._check_internet_connectivity()
        if self.is_online:
            Logger.electrum.debug('Peer %s error', peer)
            await self._handle_peer_error(peer)

    @property
    def connections(self):
        self._connections = [
            c for c in self._connections if c.protocol or (not c.protocol and c.score == c.start_score)
        ]
        return self._connections

    @property
    def established_connections(self):
        return [connection for connection in self.connections if connection.connected]

    def _pick_server(self):
        i = 0
        while 1:
            server = random.choice(self._servers)
            if server[0] not in [connection.hostname for connection in self.connections]:
                return server
            i += 1
            if i > 100:
                raise exceptions.NoServersException

    def _pick_multiple_servers(self, howmany: int):
        assert howmany >= 1
        i = 0
        servers = []
        while 1:
            server = self._pick_server()
            if server in servers:
                continue
            servers.append(server)
            if len(servers) == howmany:
                return servers
            if i > 100:
                raise exceptions.NoServersException
            i += 1

    def _pick_connection(self, fail_silent=False):
        i = 0
        while 1:
            connection = random.choice(self.established_connections)
            if connection.connected and connection.score > 0:
                return connection
            i += 1
            if i > 100:
                if not fail_silent:
                    raise exceptions.NoPeersException
                break

    def _pick_multiple_connections(self, howmany: int):
        assert howmany >= 1
        i = 0
        connections = []
        while 1:
            connection = self._pick_connection()
            if connection in connections:
                continue
            connections.append(connection)
            if len(connections) == howmany:
                return connections
            if i > 100:
                raise exceptions.NoPeersException
            i += 1

    def stop(self):
        self._keepalive = False

    async def _check_internet_connectivity(self):
        if self._network_checker is None:  # pragma: no cover
            self._is_online = True
            return
        self._is_online = self._network_checker()

    async def connect(self):
        await self._check_internet_connectivity()
        self._keepalive = True
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
            missings = int(self._required_connections - len(self.established_connections))
            if missings > 0:
                Logger.electrum.debug('ConnectionPool: connect, needed: %s', missings)
                self.loop.create_task(self._connect_servers(missings))
            elif missings < 0:
                Logger.electrum.warning('Too much peers.')
                connection = self._pick_connection(fail_silent=True)
                self.loop.create_task(connection.disconnect())
            elif not self._connection_notified:
                for observer in self._on_connect_observers:
                    self.loop.create_task(observer())
                self._connection_notified = True
            await asyncio.sleep(missings and 2 or 10)

    async def _connect_servers(self, howmany: int):
        servers = self._pick_multiple_servers(howmany)
        servers and Logger.electrum.debug('Connecting to servers (%s)', howmany)
        for server in servers:
            instance = self._connection_factory(
                hostname=server[0],
                protocol=server[1],
                keepalive=self._connections_keepalive_time,
                use_tor=self._use_tor,
                loop=self.loop,
                is_online_checker=self.is_online
            )
            instance.add_on_connect_callback(self.on_peer_connected)
            instance.add_on_header_callbacks(self.on_peer_received_header)
            instance.add_on_peers_callback(self.on_peer_received_peers)
            instance.add_on_error_callback(self.on_peer_error)
            self._connections.append(instance)
            Logger.electrum.debug('Created client instance: %s', server[0])
            self.loop.create_task(instance.connect())

    @property
    def servers(self):
        return self._servers

    async def call(self, method, params, agreement=1, get_peer=False, fail_silent=False) -> Dict:
        if get_peer and agreement > 1:
            raise ValueError('Error!')
        if agreement > self._required_connections:
            raise ValueError('Agreement requested is out of range %s' % self._required_connections)
        if agreement > len(self.established_connections):
            raise exceptions.NoPeersException

        if agreement > 1:
            servers = self._pick_multiple_connections(agreement)
            responses = await asyncio.gather(
                connection.rpc_call(method, params) for connection in servers
            )
            responses = [r for r in responses if r is not None]
            if len(responses) < agreement and not fail_silent:
                Logger.electrum.exception('call, requested %s responses, received %s', agreement, len(responses))
                Logger.electrum.debug('call, requested %s responses, received %s', agreement, responses)
                raise exceptions.ElectrodMissingResponseException
            return self._handle_responses(responses)
        connection = self._pick_connection()
        response = await connection.rpc_call(method, params)
        if not response and not fail_silent:
            raise exceptions.ElectrodMissingResponseException
        return (connection, response) if get_peer else response

    @staticmethod
    def _handle_responses(responses) -> Dict:
        if len(responses) == 1:
            return responses and responses[0]
        for response in responses:
            if responses.count(response) == len(responses):
                return response
        raise exceptions.NoQuorumOnResponsesException(responses)

    async def _handle_peer_error(self, peer: ElectrodConnection):
        Logger.electrum.debug('Handling connection error for %s', peer.hostname)
        if not peer.connected:
            return
        if not peer.score:
            Logger.electrum.error('Disconnecting from peer %s, score: %s', peer.hostname, peer.score)
            self.loop.create_task(self.delayer(peer.disconnect()))

        if not await peer.ping(timeout=2):
            Logger.electrum.error('Ping timeout from peer %s, score: %s', peer.hostname, peer.score)
            self.loop.create_task(self.delayer(peer.disconnect()))
