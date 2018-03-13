import asyncio
import os
import binascii
import random
import time
from typing import Dict, List
import async_timeout
from connectrum.client import StratumClient
from connectrum.svr_info import ServerInfo
from spruned.application.logging_factory import Logger
from spruned.daemon import exceptions


class ElectrodConnection:
    def __init__(
            self, hostname: str, protocol: str, keepalive=120,
            client=StratumClient, nickname=None, use_tor=False, loop=None,
            start_score=10, timeout=10
    ):
        self.hostname = hostname
        self.protocol = protocol
        self.keepalive = keepalive
        self.client: StratumClient = client()
        self.nickname = nickname or binascii.hexlify(os.urandom(8)).decode()
        self.use_tor = use_tor
        self._version = None
        self._on_headers_callbacks = []
        self._on_connect_callbacks = []
        self._on_disconnect_callbacks = []
        self._on_errors_callbacks = []
        self._on_peers_callbacks = []
        self.loop = loop or asyncio.get_event_loop()
        self._score = start_score
        self._last_header = None
        self._subscriptions = []
        self._timeout = timeout
        self._errors = []
        self._peers = []

    async def _task(self, task, delay=0):
        await asyncio.sleep(delay)
        await task

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

    async def on_disconnect(self, *_, **__):
        for callback in self._on_disconnect_callbacks:
            self.loop.create_task(callback(self))

    async def on_error(self, error):
        self._errors.append(error)
        self._score -= 1
        for callback in self._on_errors_callbacks:
            self.loop.create_task(callback(self))

    async def connect(self):
        try:
            self._version = await self.client.connect(
                ServerInfo(self.nickname, hostname=self.hostname, ports=self.protocol, version='1.2'),
                disconnect_callback=self.on_disconnect,
                disable_cert_verify=True,
                use_tor=self.use_tor
            )
            Logger.electrum.debug('Connected to %s', self.hostname)
            await self.on_connect()
        except Exception as e:
            self._score -= 4
            Logger.electrum.exception('Exception connecting to %s', self.hostname)
            self.on_error(e)

    @property
    def version(self):
        return self._version

    @property
    def connected(self):
        return bool(self.client.protocol)

    async def ping(self, timeout=2) -> (None, float):
        async with async_timeout.timeout(timeout):
            try:
                now = time.time()
                await self.rpc_call('server.version')
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
        return self._score

    @property
    def peers(self):
        return self._peers

    async def rpc_call(self, method: str, *args):
        try:
            async with async_timeout.timeout(self._timeout):
                return self.client.RPC(method, *args)
        except Exception as e:
            Logger.electrum.exception('call')
            self.loop.create_task(self._task(self.on_error(e)))

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
            Logger.electrum.exception('subscribe %s failed', channel)
            self.loop.create_task(self._task(self.on_error(e)))

    async def _poll_queue(self, queue: asyncio.Queue, callback):
        try:
            header = await queue.get()
            Logger.electrum.debug('new data from queue: %s', header)
            self._last_header = header[0]
            self.loop.create_task(self._task(callback(self)))
            self.loop.create_task(self._task(self._poll_queue(queue, callback)))
        except Exception as e:
            Logger.electrum.exception('queue poll failed')
            self._score -= 1
            self.loop.create_task(self._task(self.on_error(e)))

    async def disconnect(self):
        try:
            self.client.close()
        except Exception as e:
            Logger.electrum.error('Exception disconnecting from peer: %s', e)
            self.client.protocol = None


class ElectrodConnectionPool:
    def __init__(self, connections=3, loop=asyncio.get_event_loop(), use_tor=False):
        self._use_tor = use_tor
        self._servers = []
        self._connections = []
        self._required_connections = connections
        self._keepalive = None
        self.loop = loop
        self._connections_keepalive_time = 120
        self._headers_observers = []
        self._new_peers_observers = []

    async def _task(self, task, delay=0):
        await asyncio.sleep(delay)
        await task

    def add_header_observer(self, observer):
        self._headers_observers.append(observer)

    def on_peer_connected(self, peer: ElectrodConnection):
        peer.subscribe('blockchain.headers.subscribe', self.on_peer_received_header, self.on_peer_received_header)

    def on_peer_disconnected(self, peer: ElectrodConnection):
        pass

    async def on_peer_received_header(self, peer: ElectrodConnection):
        for observer in self._headers_observers:
            self.loop.create_task(self._task(observer(peer.last_header)))

    async def on_peer_received_peers(self, peer: ElectrodConnection):
        for observer in self._new_peers_observers:
            self.loop.create_task(self._task(observer(peer.peers)))

    async def on_peer_error(self, peer: ElectrodConnection):
        Logger.electrum.debug('Peer %s error', peer)
        await self._handle_peer_error(peer)

    @property
    def connections(self):
        return self._connections

    @property
    def established_connections(self):
        return [connection for connection in self._connections if connection.connected]

    def _pick_server(self):
        i = 0
        while 1:
            server = random.choice(self._servers)
            if server[0] not in [connection.hostname for connection in self.established_connections]:
                return server
            i += 1
            if i > 100:
                raise exceptions.NoPeersException

    def stop(self):
        self._keepalive = False

    async def connect(self):
        while self._keepalive:
            self.loop.create_task(self._connect_servers(self._required_connections - len(self.established_connections)))
            await asyncio.sleep(10)

    async def _connect_servers(self, howmany: int):
        servers = [self._pick_server() for _ in range(howmany)]
        for server in servers:
            instance = ElectrodConnection(
                hostname=server[0],
                protocol=server[1],
                keepalive=self._connections_keepalive_time,
                use_tor=self._use_tor,
                loop=self.loop
            )
            instance.add_on_connect_callback(self.on_peer_connected)
            instance.add_on_header_callbacks(self.on_peer_received_header)
            instance.add_on_peers_callback(self.on_peer_received_peers)
            instance.add_on_error_callback(self.on_peer_error)
            instance.add_on_error_callback(self._handle_peer_error)

            self._connections.append(instance)
            self.loop.create_task(instance.connect())

    @property
    def servers(self):
        return self._servers

    async def call(self, method, params, agreement=1) -> Dict:
        if agreement > self._required_connections:
            raise ValueError('Agreement requested is out of range %s' % self._required_connections)
        elif agreement > len(self.established_connections):
            raise exceptions.NoPeersException
        responses = await asyncio.gather(
            connection.rpc_call(method, params) for connection in self._connections
        )
        responses = [r for r in responses if r is not None]
        if len(responses) < agreement:
            Logger.electrum.exception('call, requested %s responses, received %s', agreement, len(responses))
            Logger.electrum.debug('call, requested %s responses, received %s', agreement, responses)
            raise exceptions.ElectrodMissingResponseException
        return self._handle_responses(responses)

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
            self.loop.create_task(self._task(peer.disconnect()))

        if not await peer.ping(timeout=2):
            Logger.electrum.error('Ping timeout from peer %s, score: %s', peer.hostname, peer.score)
            self.loop.create_task(self._task(peer.disconnect()))
