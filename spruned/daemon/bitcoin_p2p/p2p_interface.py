import asyncio
from typing import Dict

import time
from pycoin.serialize import h2b_rev

from spruned.dependencies.pycoinnet.pycoin.InvItem import InvItem, ITEM_TYPE_SEGWIT_BLOCK
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

    async def get_block(self, blockhash: str, peers=None, timeout=None, privileged_peers=False) -> Dict:
        inv_item = InvItem(ITEM_TYPE_SEGWIT_BLOCK, h2b_rev(blockhash))
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
        _ = [self.pool.add_peer(peer) for peer in peers]
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

    async def on_transaction_hash(self, connection, item):
        if self.mempool.add_seen(item.data, '{}/{}'.format(connection.hostname, connection.port)):
            await self.pool.get_from_connection(connection, item)

    async def on_transaction(self, connection, item):
        if self.mempool.add_seen(item['tx'].id(), '{}/{}'.format(connection.hostname, connection.port)):
            transaction = {
                "timestamp": int(time.time()),
                "txid": item["tx"].id(),
                "outpoints": ["{}:{}".format(x.previous_hash, x.previous_index) for x in item["tx"].txs_in],
                "bytes": item['tx'].as_bin()
            }
            transaction["size"] = len(transaction["bytes"])
            self.mempool.add_transaction(transaction["txid"], transaction)
