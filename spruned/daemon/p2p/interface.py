import asyncio
from typing import Dict

import typing

from pycoin.serialize import h2b_rev

from spruned.application.context import ctx
from spruned.application.logging_factory import Logger
from spruned.daemon import exceptions
from spruned.daemon.p2p.connection import P2PConnection
from spruned.daemon.p2p.connectionpool import P2PConnectionPool

from spruned.dependencies.pycoinnet.pycoin.inv_item import InvItem, \
    ITEM_TYPE_SEGWIT_BLOCK, ITEM_TYPE_BLOCK, ITEM_TYPE_MERKLEBLOCK
from spruned.dependencies.pycoinnet.networks import MAINNET
from spruned.daemon.p2p import utils


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

    def get_free_slots(self) -> int:
        return int(len(self.pool and self.pool.free_connections or []))

    async def on_connect(self):
        for callback in self._on_connect_callbacks:
            self.loop.create_task(callback())

    def add_on_connect_callback(self, callback: callable):
        self._on_connect_callbacks.append(callback)

    async def bootstrap_peers(self):
        peers = None
        #peers = [('bitcoind.mempool.co', 8333)]
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

    async def get_block(self, block_hash: str, timeout=None, segwit=True) -> Dict:
        Logger.p2p.debug('Downloading block %s' % block_hash)
        connection: P2PConnection = self.pool.get_connection()
        block_type = segwit and ITEM_TYPE_SEGWIT_BLOCK or ITEM_TYPE_BLOCK
        inv_item = InvItem(block_type, h2b_rev(block_hash))
        response = (await connection.get_invitem(inv_item, timeout=timeout)).response
        return response and {
            "block_hash": str(block_hash),
            "header_bytes": response[:80],
            "block_bytes": response
        }

    async def get_headers_after_hash(
            self,
            *start_from_hash: str,
            stop_at_hash: typing.Optional[str] = None,
            connection: typing.Optional[P2PConnection] = None
    ):
        connection: P2PConnection = connection or self.pool.get_connection()
        await connection.getheaders(*start_from_hash, stop_at_hash=stop_at_hash)
        return connection

    def get_current_peers_best_height(self) -> int:
        # todo find a better agreement than "max"
        if not self.pool.established_connections:
            raise exceptions.NoPeersException
        return max(
            map(
                lambda connection: connection.last_block_index,
                filter(
                    lambda c: c.last_block_index,
                    self.pool.established_connections
                )
            )
        )
