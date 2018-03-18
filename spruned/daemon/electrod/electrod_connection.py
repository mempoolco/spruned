import asyncio
import os
import binascii
import time
from typing import Dict, List
import async_timeout
from connectrum.client import StratumClient
from connectrum.svr_info import ServerInfo
from spruned.application.logging_factory import Logger
from spruned.application.tools import async_delayed_task, check_internet_connection
from spruned.daemon import exceptions
from spruned.daemon.abstracts import ConnectionAbstract
from spruned.daemon.connection_base_impl import BaseConnectionPool


class ElectrodConnection(ConnectionAbstract):
    def __init__(
            self, hostname: str, protocol: str, keepalive=180,
            client=StratumClient, serverinfo=ServerInfo, nickname=None, use_tor=False, loop=None,
            start_score=10, timeout=10, expire_errors_after=180,
            is_online_checker: callable=None, delayer=async_delayed_task
    ):
        self._hostname = hostname
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

    @property
    def hostname(self):
        return self._hostname

    def add_error(self, *a):
        if len(a) and isinstance(a[0], int):
            self._errors.append(a[0])
        else:
            self._errors.append(int(time.time()))

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

    async def on_peers(self):
        for callback in self._on_peers_callbacks:
            self.loop.create_task(callback(self))

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

    async def rpc_call(self, method: str, args):
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
            Logger.electrum.error('queue poll failed')
            self.loop.create_task(self.delayer(self.on_error(e)))

    async def disconnect(self):
        try:
            self.client.close()
        except Exception as e:
            Logger.electrum.error('Exception disconnecting from peer: %s', e)
            self.client.protocol = None


class ElectrodConnectionPool(BaseConnectionPool):
    def __init__(
            self,
            connection_factory=ElectrodConnection,
            peers=list(),
            network_checker=check_internet_connection,
            delayer=async_delayed_task,
            loop=asyncio.get_event_loop(),
            use_tor=False,
            connections=3,
            sleep_no_internet=30
    ):
        super().__init__(
            peers=peers, network_checker=network_checker, delayer=delayer,
            loop=loop, use_tor=use_tor, connections=connections, sleep_no_internet=sleep_no_internet
        )
        self._connections_keepalive_time = 120
        self._connection_factory = connection_factory

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
        peers = self._pick_multiple_peers(howmany)
        peers and Logger.electrum.debug('Connecting to peers (%s)', howmany)
        for peer in peers:
            instance = self._connection_factory(
                hostname=peer[0],
                protocol=peer[1],
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
            Logger.electrum.debug('Created client instance: %s', peer[0])
            self.loop.create_task(instance.connect())

    async def call(self, method, *params, agreement=1, get_peer=False, fail_silent=False) -> (None, Dict):
        if get_peer and agreement > 1:
            raise ValueError('Error!')
        if agreement > self._required_connections:
            raise ValueError('Agreement requested is out of range %s' % self._required_connections)
        if agreement > len(self.established_connections):
            raise exceptions.NoPeersException

        if agreement > 1:
            connections = self._pick_multiple_connections(agreement)
            responses = await asyncio.gather(
                *[connection.rpc_call(method, params) for connection in connections]
            )
            responses = [r for r in responses if r is not None]
            if len(responses) < agreement:
                Logger.electrum.exception('call, requested %s responses, received %s', agreement, len(responses))
                Logger.electrum.debug('call, requested %s responses, received %s', agreement, responses)
                if fail_silent:
                    return
                raise exceptions.ElectrodMissingResponseException
            try:
                return self._handle_responses(responses)
            except exceptions.NoQuorumOnResponsesException:
                if fail_silent:
                    return
                raise
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

    def on_peer_received_peers(self, peer: ConnectionAbstract):
        raise NotImplementedError