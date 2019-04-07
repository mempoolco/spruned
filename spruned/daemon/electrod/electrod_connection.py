import asyncio
import os
import binascii
import time
from typing import Dict
import async_timeout

from spruned.dependencies.connectrum import ElectrumErrorResponse
from spruned.dependencies.connectrum import StratumClient
from spruned.dependencies.connectrum import ServerInfo

from spruned.application.context import ctx
from spruned.application.logging_factory import Logger
from spruned.application.tools import async_delayed_task, check_internet_connection
from spruned.daemon import exceptions
from spruned.daemon.connection_base_impl import BaseConnection
from spruned.daemon.connectionpool_base_impl import BaseConnectionPool
from spruned.daemon.electrod import save_electrum_servers


class ElectrodConnection(BaseConnection):
    def __init__(
            self, hostname: str, protocol: str, keepalive=180,
            client=StratumClient, serverinfo=ServerInfo, nickname=None, proxy=False, loop=None,
            start_score=10, timeout=30, expire_errors_after=180,
            is_online_checker: callable=None, delayer=async_delayed_task, network=ctx.get_network()
    ):

        self.protocol = protocol
        self.port = self.protocol
        self.keepalive = keepalive
        self.client = client()
        self.serverinfo_factory = serverinfo
        self.client.keepalive_interval = keepalive
        self.nickname = nickname or binascii.hexlify(os.urandom(8)).decode()
        self.network = network
        super().__init__(
            hostname=hostname, proxy=proxy, loop=loop, start_score=start_score,
            is_online_checker=is_online_checker, timeout=timeout, delayer=delayer,
            expire_errors_after=expire_errors_after
        )
        self.starting_height = None

    @property
    def proxy(self):
        return self._proxy and 'socks5://{}'.format(self._proxy)

    @property
    def subversion(self):
        return self._version and self._version[0]

    @property
    def connected(self):
        return bool(self.client.protocol)

    async def connect(self, ignore_version=False, disable_callbacks=False, short_term=False):
        try:
            with async_timeout.timeout(self._timeout):
                await self.client.connect(
                    self.serverinfo_factory(self.nickname, hostname=self.hostname, ports=self.protocol, version="1.4"),
                    disconnect_callback=not disable_callbacks and self.on_connectrum_disconnect,
                    disable_cert_verify=True,
                    proxy=self.proxy,
                    ignore_version=ignore_version,
                    short_term=short_term
                )
                self._version = self.client.server_version
                Logger.electrum.info(
                    'Connected to peer %s:%s (%s)', self.hostname, self.port, self.version and self.version[0]
                )
                Logger.electrum.debug('Peer raw response: %s', self.version)
                if not ignore_version:
                    res = await self.rpc_call(
                        'blockchain.transaction.get', [self.network['tx1'], 1]
                    )
                    if not isinstance(res, dict) or not res['blockhash'] == self.network['checkpoints'][1]:
                        raise ValueError
                self.connected_at = int(time.time())
                if not disable_callbacks:
                    await self.on_connect()
        except Exception as e:
            Logger.electrum.debug('Exception connecting to %s (%s)', self.hostname, e)
            if not disable_callbacks:
                await self.on_error('connect')

    def on_connectrum_disconnect(self, *_, **__):
        for callback in self._on_disconnect_callbacks:
            self.loop.create_task(callback(self))

    async def ping(self, timeout=2) -> (None, float):
        try:
            async with async_timeout.timeout(timeout):
                now = time.time()
                await self.client.RPC('server.ping')
                return time.time() - now
        except asyncio.TimeoutError:
            return

    async def rpc_call(self, method: str, args):
        try:
            async with async_timeout.timeout(self._timeout):
                return await self.client.RPC(method, *args)
        except asyncio.InvalidStateError:
            raise
        except ElectrumErrorResponse as e:
            if e.args and isinstance(e.args[0], dict):
                return e.args[0]
        except Exception as e:
            Logger.electrum.warning(
                'exception on rpc call: %s, %s, %s', self.client.server_info, self.client.protocol, e
            )
            self.loop.create_task(self.delayer(self.on_error(e)))

    async def subscribe(self, channel: str, on_subscription: callable, on_traffic: callable):
        try:
            async with async_timeout.timeout(self._timeout):
                future, q = self.client.subscribe(channel)
            self.subscriptions.append({channel: q})
            header = await future
            self.starting_height = header['height']
            self._last_header = header
            on_subscription and self.loop.create_task(on_subscription(self))
            self.loop.create_task(self._poll_queue(q, on_traffic))
        except Exception as e:
            Logger.electrum.error('subscribe %s on %s failed', channel, self.hostname, exc_info=True)
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
            proxy=False,
            connections=3,
            sleep_no_internet=30,
            rpc_call_timeout=30,
            servers_storage=save_electrum_servers,
            ipv6=False,
            tor=False
    ):
        super().__init__(
            peers=peers, network_checker=network_checker, delayer=delayer,
            loop=loop, proxy=proxy, connections=connections, sleep_no_internet=sleep_no_internet,
            ipv6=ipv6
        )
        self._connections_keepalive_time = 120
        self._connection_factory = connection_factory
        self.rpc_call_timeout = rpc_call_timeout
        self.servers_storage = servers_storage
        self._storage_lock = asyncio.Lock()
        self.tor = tor

    @property
    def proxy(self):
        return self._proxy

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
                Logger.electrum.warning('Too many peers.')
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
                proxy=self.proxy,
                loop=self.loop,
                is_online_checker=self.is_online,
                timeout=self.rpc_call_timeout
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
            await self.on_peer_error(connection)
            raise exceptions.ElectrodMissingResponseException(connection)
        return (connection, response) if get_peer else response

    @staticmethod
    def _handle_responses(responses) -> Dict:
        if len(responses) == 1:
            return responses and responses[0]
        for response in responses:
            if responses.count(response) == len(responses):
                return response
        raise exceptions.NoQuorumOnResponsesException(responses)

    def on_peer_received_peers(self, peer: ElectrodConnection, *_):
        raise NotImplementedError

    async def on_peer_connected(self, peer: ElectrodConnection):
        future = peer.subscribe(
            'blockchain.headers.subscribe',
            self.on_peer_received_header,
            self.on_peer_received_header
        )
        self.loop.create_task(self.delayer(future))
        self.loop.create_task(self.save_peers(peer))

    async def save_peers(self, peer: ElectrodConnection):
        await self._storage_lock.acquire()
        try:
            peers = set()
            _peers = await peer.rpc_call('server.peers.subscribe', []) or []
            for peer in _peers:
                if peer[2][0] == 'v1.4':
                    peers.add(peer[0])
            self.servers_storage(peers)
        finally:
            self._storage_lock.release()

    def get_peer_for_hostname(self, hostname: str):
        for peer in self.established_connections:
            if hostname == peer.hostname:
                return peer
