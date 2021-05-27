import asyncio
import itertools

import aiohttp_socks
import async_timeout
import time

import typing

from spruned.application.logging_factory import Logger
from spruned.application.tools import async_delayed_task
from spruned.services import exceptions
from spruned.services.connection_base_impl import BaseConnection
from spruned.services.exceptions import PeerBlockchainBehindException, PeerVersionMismatchException
from spruned.services.p2p.channel import P2PChannel
from spruned.services.p2p.types import P2PInvItemResponse
from spruned.dependencies.pycoinnet.peer import Peer, ProtocolError
from spruned.dependencies.pycoinnet.networks import MAINNET, Network
from spruned.dependencies.pycoinnet.pycoin.inv_item import ITEM_TYPE_TX, InvItem
from spruned.dependencies.pycoinnet.version import make_local_version, NODE_NONE, NODE_WITNESS


def connector_f(host: str = None, port: int = None, proxy: str = None):
    if proxy:
        return aiohttp_socks.open_connection(socks_url=proxy, host=host, port=port)
    return asyncio.open_connection(host=host, port=port)


class P2PConnection(BaseConnection):
    def __init__(
            self,
            hostname: str,
            port: int,
            peer=Peer,
            network: Network = MAINNET,
            loop=asyncio.get_event_loop(),
            proxy: typing.Optional[str] = None,
            start_score: int = 10,
            is_online_checker: typing.Optional[callable] = None,
            timeout: int = 10,
            delayer: callable = async_delayed_task,
            expire_errors_after: int = 180,
            call_timeout: int = 5,
            connector: callable = connector_f,
            bloom_filter=None,
            best_header: typing.Dict = None,
            version_checker: callable = None
    ):

        super().__init__(
            hostname=hostname,
            proxy=proxy,
            loop=loop,
            start_score=start_score,
            is_online_checker=is_online_checker,
            timeout=timeout,
            delayer=delayer,
            expire_errors_after=expire_errors_after
        )
        self._bloom_filter = bloom_filter
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
        self._on_transaction_hash_callbacks = []
        self._on_addr_callbacks = []
        self.connector = connector
        self.best_header = best_header
        self.last_block_index = None
        self.version_checker = version_checker
        self.failed = False
        self._antispam = []
        self.pool = None

    def ping(self, timeout=None):
        self.peer.send_msg('ping', int(time.time()))

    @property
    def proxy(self):
        proxy = self._proxy and self._proxy.split(':')
        return proxy and len(proxy) > 1 and 'socks5://{}:{}'.format(proxy[0], proxy[1])

    @property
    def subversion(self):
        return self._version and self._version.get('subversion', b'').decode().strip('/')

    @property
    def connected(self):
        return bool(self.peer)

    def add_on_blocks_callback(self, callback: callable):
        self._on_block_callbacks.append(callback)

    def add_on_transaction_hash_callback(self, callback: callable):
        self._on_transaction_hash_callbacks.append(callback)

    def add_on_transaction_callback(self, callback: callable):
        self._on_transaction_callbacks.append(callback)

    def add_on_addr_callback(self, callback: callable):
        self._on_addr_callbacks.append(callback)

    def add_on_headers_callback(self, callback: callable):
        self._on_headers_callbacks.append(callback)

    @property
    def peer_event_handler(self) -> P2PChannel:
        return self._event_handler

    def add_error(self, *a, origin=None):
        super().add_error(*a, origin=origin)
        Logger.p2p.error('Adding error to connection, origin: %s, score: %s', origin, self.score)
        self._score -= 1
        if self.score <= 0:
            self.loop.create_task(self.disconnect())

    def add_request(self):
        self._score -= 1

    def add_success(self, score=1):
        self._score = min(self._score + score, self.max_score)

    async def _handle_connect(self):
        try:
            reader, writer = await self.connector(
                host=self.hostname,
                port=self.port,
                proxy=self.proxy
            )
        except (
                ConnectionError,
                OSError,
                asyncio.exceptions.TimeoutError,
                asyncio.exceptions.CancelledError
        ) as e:
            raise exceptions.PeerHandshakeException from e

        peer = self._peer_factory(
            reader,
            writer,
            self._peer_network.magic_header,
            self._peer_network.parse_from_data,
            self._peer_network.pack_from_data
        )
        version_msg = make_local_version(
            peer,
            version=70015,
            local_services=NODE_NONE,
            remote_services=NODE_WITNESS,
            relay=self.pool.enable_mempool
        )
        try:
            version_data = await self._verify_peer(await peer.perform_handshake(**version_msg))
        except (
                PeerBlockchainBehindException,
                PeerVersionMismatchException,
                ProtocolError,
                asyncio.exceptions.TimeoutError,
                asyncio.exceptions.CancelledError
        ) as e:
            raise exceptions.PeerHandshakeException from e

        self.last_block_index = version_data['last_block_index']
        self._event_handler = P2PChannel(self)
        self._version = version_data

        Logger.p2p.info(
            'Connected to peer %s:%s (%s)', self.hostname, self.port,
            self.version and self.version.get('subversion', b'').decode().strip('/')
        )
        Logger.p2p.debug('Peer raw response %s', self.version)
        self._do_more_handshake(peer)
        self.peer = peer
        self.connected_at = int(time.time())
        self._setup_events_handler()

    def _do_more_handshake(self, peer):
        peer.send_msg('sendheaders')
        if self._bloom_filter:
            filter_bytes, hash_function_count, tweak = self._bloom_filter.filter_load_params()
            flags = 0
            peer.send_msg(
                "filterload",
                filter=filter_bytes,
                hash_function_count=hash_function_count,
                tweak=tweak,
                flags=flags
            )

    async def connect(self):
        try:
            async with async_timeout.timeout(5):
                await self._handle_connect()
        except exceptions.PeerHandshakeException as e:
            Logger.p2p.debug('Exception connecting to %s (%s)', self.hostname, str(e))
            self._on_connection_failed()
            return

        except Exception as e:
            Logger.p2p.exception('Exception connecting to %s (%s)', self.hostname, str(e))
            self._on_connection_failed()
            return

        self.loop.create_task(self.on_connect())
        return self

    def _on_connection_failed(self):
        self.peer = None
        self.failed = True
        self.loop.create_task(self.on_error('connect'))
        return

    async def _verify_peer(self, version_data: typing.Dict):
        if self.best_header and self.best_header['block_height'] - version_data['last_block_index'] > 5:
            await self.disconnect()
            raise exceptions.PeerBlockchainBehindException
        if self.version_checker and not self.version_checker(version_data):
            self.pool.ban_peer((self.hostname, self.port))
            await self.disconnect()
            raise exceptions.PeerVersionMismatchException
        return version_data

    async def on_connect(self):
        for callback in self._on_connect_callbacks:
            self.loop.create_task(callback(self))

    async def disconnect(self):
        self.failed = True
        Logger.p2p.debug(
            'Disconnecting peer %s (%s)' % (self.hostname, self.version and self.version.get('subversion'))
        )
        self.pool.ban_peer((self.hostname, self.port))
        self.peer and self.peer.close()
        self.peer = None
        self.pool.cleanup_connections()

    def _setup_events_handler(self):
        self.peer_event_handler.set_event_callbacks('inv', self._on_inv)
        self.peer_event_handler.set_event_callbacks('addr', self._on_addr)
        self.peer_event_handler.set_event_callbacks('alert', self._on_alert)
        self.peer_event_handler.set_event_callbacks('ping', self._on_ping)
        self.peer_event_handler.set_event_callbacks('headers', self._on_headers)
        self.peer_event_handler.set_event_callbacks('feefilter', self._dummy_handler)
        self.peer_event_handler.set_event_callbacks('sendcmpct', self._dummy_handler)
        self.peer_event_handler.set_event_callbacks('tx', self._on_tx_inv)

    def _dummy_handler(self, *a, **kw):
        pass

    def _on_tx_inv(self, event_handler: P2PChannel, name: str, data: typing.Dict):
        for callback in self._on_transaction_callbacks:
            self.loop.create_task(callback(self, data))

    def _on_inv(self, event_handler: P2PChannel, name: str, data: typing.Dict):
        self.loop.create_task(self._process_inv(event_handler, name, data))

    @staticmethod
    def _on_alert(event_handler: P2PChannel, name: str, data: typing.Dict):  # pragma: no cover
        Logger.p2p.debug('Handle alert: %s, %s, %s', event_handler, name, data)

    def _on_addr(self, event_handler: P2PChannel, name: str, data: typing.Dict):  # pragma: no cover
        peers = []
        for peer in data['date_address_tuples']:
            host, port = str(peer[1]).split('/')
            port = int(port)
            peers.append([host, port])
        for callback in self._on_addr_callbacks:
            self.loop.create_task(callback(peers))

    def _on_headers(self, event_handler: P2PChannel, name: str, data: typing.Dict):  # pragma: no cover
        headers = data['headers']
        if not headers:
            Logger.p2p.debug('Received from peer %s empty on_headers: %s', event_handler, data)
            return
        for callback in self._on_headers_callbacks:
            self.loop.create_task(callback(self, headers))

    def _on_ping(self, event_handler: P2PChannel, name: str, data: typing.Dict):
        self.peer.send_msg("pong", nonce=data["nonce"])
        Logger.p2p.debug('Handle ping: %s, %s, %s', event_handler, name, data)

    async def _process_inv(self, event_handler: P2PChannel, name: str, data: typing.Dict):
        txs = 0
        for item in data.get('items'):
            if item.item_type == ITEM_TYPE_TX:
                txs += 1
                for callback in self._on_transaction_hash_callbacks:
                    self.loop.create_task(callback(self, item))
            else:
                Logger.p2p.debug('Unhandled InvType: %s, %s, %s', event_handler, name, item)
        Logger.p2p.debug('Received %s items, txs: %s', len(data.get('items')), txs)

    async def get_invitem(self, inv_item: InvItem, timeout: int) -> P2PInvItemResponse:
        """
        get data from a peer or fail, return the related peer with the response
        """
        self.add_request()
        done, pending = await asyncio.wait(
            (self.peer_event_handler.get_inv_item(inv_item),),
            timeout=timeout
        )
        if not done:
            _ = map(
                lambda x: x.cancel(),
                filter(lambda x: not x.done(), itertools.chain(done, pending))
            )
            self.add_error(int(time.time()), origin='get_invitem')
            raise exceptions.MissingPeerResponseException
        self.add_success()
        return P2PInvItemResponse(
            response=done.pop().result(),
            connection=self
        )

    async def getaddr(self):
        self.peer.send_msg("getaddr")

    async def getheaders(self, *start_from_hash: str, stop_at_hash: typing.Optional[str] = None):
        self.add_request()
        if stop_at_hash is not None:
            assert len(stop_at_hash) == 64

        for x in start_from_hash:
            assert len(x) == 64, x
        self.peer.send_msg(
            "getheaders",
            version=70015,
            hash_count=len(start_from_hash),
            hashes=[bytes.fromhex(s)[::-1] for s in start_from_hash],
            hash_stop=bytes.fromhex(stop_at_hash or '0'*64)
        )

    async def fetch_headers_blocking(self, *start_from_hash: str, stop_at_hash: typing.Optional[str]):
        self.add_request()
        if stop_at_hash is not None:
            assert len(stop_at_hash) == 64, stop_at_hash

        for x in start_from_hash:
            assert len(x) == 64, x
        return await self.peer_event_handler.get(
            "getheaders",
            start_from_hash[0],
            dict(
                version=70015,
                hash_count=len(start_from_hash),
                hashes=[bytes.fromhex(s)[::-1] for s in start_from_hash],
                hash_stop=bytes.fromhex(stop_at_hash)
            )
        )
