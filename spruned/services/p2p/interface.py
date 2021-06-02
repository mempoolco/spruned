import asyncio
from typing import Dict

import typing

from pycoin.serialize import h2b_rev

from spruned.application import consensus
from spruned.application.context import ctx
from spruned.application.logging_factory import Logger
from spruned.services import exceptions
from spruned.services.p2p.connection import P2PConnection
from spruned.services.p2p.connectionpool import P2PConnectionPool

from spruned.dependencies.pycoinnet.pycoin.inv_item import InvItem, \
    ITEM_TYPE_SEGWIT_BLOCK, ITEM_TYPE_BLOCK, ITEM_TYPE_MERKLEBLOCK
from spruned.dependencies.pycoinnet.networks import MAINNET
from spruned.services.p2p import utils
from spruned.utils import async_retry


class P2PInterface:
    def __init__(
            self,
            connection_pool: P2PConnectionPool,
            loop=asyncio.get_event_loop(),
            network=MAINNET,
            peers_bootstrapper=utils.dns_bootstrap_servers,
            mempool_repository=None
    ):
        self.pool: P2PConnectionPool = connection_pool
        self._on_connect_callbacks = []
        self.loop = loop
        self.network = network
        self._bootstrap_status = 0
        self._get_peers_from_seed = peers_bootstrapper
        self.mempool = mempool_repository

    def is_connected(self):
        return bool(len(self.pool.established_connections))

    async def on_peer_disagreement(self, local_header: typing.Dict, peer: P2PConnection):
        pass  # TODO FIXME
        """
        - track disagreements
        - evaluate consensus-disagreements 
        """

    @async_retry(retries=2, wait=0.1, on_exception=exceptions.RetryException)
    async def _check_connection_sync(self, connection: P2PConnection, header: typing.Dict):
        headers = await connection.fetch_headers_blocking(
            header['prev_block_hash'],
            stop_at_hash=header['block_hash']
        )
        pass

    def set_local_current_header(self, header: typing.Dict):
        for connection in self.pool.connections:
            if connection.last_block_index and connection.last_block_index < header['block_height']:
                self.loop.create_task(self._check_connection_sync(connection, header))
        self.pool.set_local_current_header(header)

    def get_free_slots(self) -> int:
        try:
            return int(len(self.pool and self.pool.free_connections or []))
        except exceptions.NoConnectionsAvailableException:
            return 0

    async def on_connect(self):
        for callback in self._on_connect_callbacks:
            self.loop.create_task(callback())

    def add_on_connect_callback(self, callback: callable):
        self._on_connect_callbacks.append(callback)

    async def bootstrap_peers(self):
        peers = None
        while not peers:
            peers = await self._get_peers_from_seed(self.network)
            await asyncio.sleep(1)
        for p in peers:
            if ctx.tor:
                '.onion' in p and self.pool.add_peer(p)
            else:
                '.onion' not in p and self.pool.add_peer(p)

    async def start(self):
        self.pool.add_on_connected_observer(self.on_connect)
        await self.bootstrap_peers()
        await self.pool.connect()

    def set_bootstrap_status(self, value: float):
        self._bootstrap_status = value

    @property
    def bootstrap_status(self):
        return self._bootstrap_status

    def get_connections(self) -> typing.List[P2PConnection]:
        return self.pool.established_connections

    async def get_merkleblock(self, block_hash: str):
        Logger.p2p.debug('Downloading merkleblock %s' % block_hash)
        connection: P2PConnection = self.pool.get_connection()
        inv_item = InvItem(ITEM_TYPE_MERKLEBLOCK, bytes.fromhex(block_hash)[::-1])
        return await connection.get_invitem(inv_item, timeout=10)

    async def get_block(
            self, block_hash: str, segwit=True, retries=10,  wait_on_fail=5, timeout=15
    ) -> Dict:

        @async_retry(retries=retries, wait=wait_on_fail, on_exception=(
            exceptions.MissingPeerResponseException,
            exceptions.NoConnectionsAvailableException
        ))
        async def _get_and_retry():
            Logger.p2p.debug('Downloading block %s' % block_hash)
            connection: P2PConnection = self.pool.get_connection()
            block_type = segwit and ITEM_TYPE_SEGWIT_BLOCK or ITEM_TYPE_BLOCK
            inv_item = InvItem(block_type, h2b_rev(block_hash))
            return (await connection.get_invitem(inv_item, timeout=timeout)).response
        response = await _get_and_retry()

        return response and {
            "block_hash": str(block_hash),
            "header_bytes": response['header_bytes'],
            "block_bytes": response['data'].read()
        }

    async def request_block(self, block_hash: bytes, segwit=True):
        connection: P2PConnection = self.pool.get_connection()
        block_type = segwit and ITEM_TYPE_SEGWIT_BLOCK or ITEM_TYPE_BLOCK
        inv_item = InvItem(block_type, block_hash[::-1])
        connection.add_request()
        await connection.request_invitem(inv_item)

    async def get_headers_after_hash(
            self,
            *start_from_hash: str,
            stop_at_hash: typing.Optional[str] = None,
            connection: typing.Optional[P2PConnection] = None
    ):
        connection: P2PConnection = connection or self.pool.get_connection(use_busy=True)
        await connection.getheaders(*start_from_hash, stop_at_hash=stop_at_hash)
        return connection

    def get_current_peers_best_height(self) -> int:
        if not self.pool.established_connections:
            raise exceptions.NoPeersException
        last_heights = list(
            map(
                lambda connection: connection.last_block_index,
                filter(
                    lambda c: c.last_block_index,
                    self.pool.established_connections
                )
            )
        )
        scores = consensus.score_values(*last_heights)
        network_height = int(scores[0]['value'])
        return network_height
