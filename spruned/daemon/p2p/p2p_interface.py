import asyncio
from typing import Dict, List
from pycoin.message.InvItem import ITEM_TYPE_BLOCK, InvItem
from pycoin.serialize import h2b_rev
from pycoinnet.networks import MAINNET

from spruned.application import exceptions
from spruned.daemon.p2p import utils
from spruned.daemon.p2p.p2p_connection import P2PConnectionPool


class P2PInterface:
    def __init__(self, connection_pool: P2PConnectionPool, loop=asyncio.get_event_loop(), network=MAINNET):
        self.pool = connection_pool
        self._on_connect_callbacks = []
        self.loop = loop
        self.network = network
        self._bootstrap_status = 0

    async def on_connect(self):
        for callback in self._on_connect_callbacks:
            self.loop.create_task(callback())

    async def get_block(self, blockhash: str, peers=None, timeout=None) -> Dict:
        inv_item = InvItem(ITEM_TYPE_BLOCK, h2b_rev(blockhash))
        response = await self.pool.get(inv_item, peers=peers, timeout=timeout)
        return response and {
            "block_hash": str(response.hash()),
            "prev_block_hash": str(response.previous_block_hash),
            "timestamp": int(response.timestamp),
            "header_bytes": bytes(response.as_blockheader().as_bin()),
            "block_object": response,
            "block_bytes": bytes(response.as_bin())
        }

    async def get_blocks(self, start: str, stop: str, max: int) -> List[Dict]:
        pass

    def add_on_connect_callback(self, callback):
        self._on_connect_callbacks.append(callback)

    async def start(self):
        self.pool.add_on_connected_observer(self.on_connect)
        peers = None
        i = 0
        while not peers:
            if i > 10:
                raise exceptions.SprunedException
            peers = await utils.dns_bootstrap_servers(self.network)
            i += 1
        _ = [self.pool.add_peer(peer) for peer in peers]
        self.loop.create_task(self.pool.connect())

    def set_bootstrap_status(self, value: float):
        self._bootstrap_status = value

    @property
    def bootstrap_status(self):
        return self._bootstrap_status