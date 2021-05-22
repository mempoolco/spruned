import asyncio
from typing import Dict
from pycoin.serialize import h2b_rev
from spruned.application.context import ctx
from spruned.application.logging_factory import Logger

from spruned.dependencies.pycoinnet.pycoin.InvItem import InvItem, ITEM_TYPE_SEGWIT_BLOCK, ITEM_TYPE_BLOCK
from spruned.dependencies.pycoinnet.networks import MAINNET
from spruned.application import exceptions
from spruned.daemon.p2p import utils
from spruned.daemon.p2p.p2p_connection import P2PConnectionPool


class P2PInterface:
    def __init__(
            self,
            connection_pool: P2PConnectionPool,
            loop=asyncio.get_event_loop(),
            network=MAINNET,
            peers_bootstrapper=utils.dns_bootstrap_servers,
            mempool_repository=None
    ):
        self.pool = connection_pool
        self._on_connect_callbacks = []
        self.loop = loop
        self.network = network
        self._bootstrap_status = 0
        self.peers_bootstrap = peers_bootstrapper
        self.mempool = mempool_repository

    def get_free_slots(self) -> int:
        return int(len(self.pool and self.pool.free_connections or []))

    async def on_connect(self):
        for callback in self._on_connect_callbacks:
            self.loop.create_task(callback())

    async def get_block(self, block_hash: str, timeout=None, segwit=True) -> Dict:
        Logger.p2p.debug('Downloading block %s' % block_hash)
        block_type = segwit and ITEM_TYPE_SEGWIT_BLOCK or ITEM_TYPE_BLOCK
        inv_item = InvItem(block_type, h2b_rev(block_hash))
        response = await self.pool.get(inv_item, timeout=timeout)
        return response and {
            "block_hash": str(block_hash),
            "header_bytes": response[:80],
            "block_bytes": response
        }

    async def get_blocks(self, *block_hash: str) -> Dict:
        sorted_hash = list(block_hash)
        blocks = {}
        retry, max_retry = 0, 100

        def _save_block(block):
            nonlocal blocks
            blocks[block['block_hash']] = block

        while sorted_hash:
            _blocks = map(
                _save_block,
                filter(
                    lambda b: b and not isinstance(b, Exception),
                    await asyncio.gather(*map(self.get_block, sorted_hash), return_exceptions=True)
                )
            )
            sorted_hash = [h for h in sorted_hash if h not in blocks]
            retry += 1
            if sorted_hash and retry > max_retry:
                raise exceptions.TooManyRetriesException
        return blocks

    def add_on_connect_callback(self, callback: callable):
        self._on_connect_callbacks.append(callback)

    async def bootstrap_peers(self):
        peers = None
        while not peers:
            peers = await self.peers_bootstrap(self.network)
            await asyncio.sleep(1)
        if ctx.tor:
            _ = map(self.pool.add_peer, filter(lambda peer: '.onion' in peer, peers))  # fixme move this check out
        else:
            _ = map(self.pool.add_peer, filter(lambda peer: '.onion' not in peer, peers))

    async def start(self):
        self.pool.add_on_connected_observer(self.on_connect)
        await self.bootstrap_peers()
        self.loop.create_task(self.pool.connect())

    def set_bootstrap_status(self, value: float):
        self._bootstrap_status = value

    @property
    def bootstrap_status(self):
        return self._bootstrap_status

    def get_peers(self):
        return list(self.pool.established_connections)
