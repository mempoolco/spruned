import asyncio
from typing import Dict
from pycoin.serialize import h2b_rev
from spruned.application.context import ctx

from spruned.dependencies.pycoinnet.pycoin.InvItem import InvItem, ITEM_TYPE_SEGWIT_BLOCK, ITEM_TYPE_BLOCK
from spruned.dependencies.pycoinnet.networks import MAINNET
from spruned.application import exceptions
from spruned.daemon.bitcoin_p2p import utils
from spruned.daemon.bitcoin_p2p.p2p_connection import P2PConnectionPool


class P2PInterface:
    def __init__(self,
                 connection_pool: P2PConnectionPool, loop=asyncio.get_event_loop(),
                 network=MAINNET, peers_bootstrapper=utils.dns_bootstrap_servers,
                 mempool_repository=None):
        self.pool = connection_pool
        self._on_connect_callbacks = []
        self.loop = loop
        self.network = network
        self._bootstrap_status = 0
        self.peers_bootstrapper = peers_bootstrapper
        self.mempool = mempool_repository

    async def on_connect(self):
        for callback in self._on_connect_callbacks:
            self.loop.create_task(callback())

    async def get_block(self, blockhash: str, peers=None, timeout=None, privileged_peers=False, segwit=True) -> Dict:
        block_type = segwit and ITEM_TYPE_SEGWIT_BLOCK or ITEM_TYPE_BLOCK
        inv_item = InvItem(block_type, h2b_rev(blockhash))
        response = await self.pool.get(inv_item, peers=peers, timeout=timeout, privileged=privileged_peers)
        return response and {
            "block_hash": str(blockhash),
            "header_bytes": response[:80],
            "block_bytes": response
        }

    async def get_blocks(self, *blockhash: str) -> Dict:
        """
        I have to work on pycoinnet to understand how the invbatcher can handle a more efficient 'getblocks'.
        Meanwhile, parallelize getblocks. This may be dirty, let's try it....
        """
        sorted_hash = [x for x in blockhash]
        blocks = {}
        r, max_retry = 0, 100
        while sorted_hash:
            r += 1
            if r > max_retry:
                raise ValueError
            _blocks = await asyncio.gather(*(self.get_block(h) for h in sorted_hash), return_exceptions=True)
            for i, _hash in enumerate(sorted_hash):
                if isinstance(_blocks[i], dict):
                    blocks[_hash] = _blocks[i]
            sorted_hash = [h for h in sorted_hash if h not in blocks]
        return blocks

    def add_on_connect_callback(self, callback):
        self._on_connect_callbacks.append(callback)

    async def start(self):
        self.pool.add_on_connected_observer(self.on_connect)
        peers = None
        i = 0
        while not peers:
            if i > 10:
                raise exceptions.SprunedException
            peers = await self.peers_bootstrapper(self.network)
            i += 1
        if ctx.tor:
            _ = [self.pool.add_peer(peer) for peer in peers if '.onion' in peer]
        else:
            _ = [self.pool.add_peer(peer) for peer in peers if '.onion' not in peer]
        self.loop.create_task(self.pool.connect())

    def set_bootstrap_status(self, value: float):
        self._bootstrap_status = value

    @property
    def bootstrap_status(self):
        return self._bootstrap_status

    def get_peers(self):
        return [
            peer for peer in self.pool.established_connections
        ]
