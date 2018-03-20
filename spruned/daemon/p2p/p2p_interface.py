import asyncio
import logging
from typing import Dict, List

import sys

import time

from pycoin.block import Block
from pycoin.message.InvItem import ITEM_TYPE_BLOCK, InvItem, ITEM_TYPE_MERKLEBLOCK, ITEM_TYPE_TX
from pycoin.serialize import h2b_rev, h2b
from pycoin.tx import Tx
from pycoinnet.networks import MAINNET

from spruned.daemon.p2p import utils
from spruned.daemon.p2p.p2p_connection import P2PConnectionPool


class P2PInterface:
    def __init__(self, connection_pool: P2PConnectionPool, loop=asyncio.get_event_loop(), network=MAINNET):
        self.pool = connection_pool
        self._on_connect_callbacks = []
        self.loop = loop
        self.network = network

    async def on_connect(self):
        for callback in self._on_connect_callbacks:
            self.loop.create_task(callback())

    async def get_block(self, blockhash: str) -> Dict:
        inv_item = InvItem(ITEM_TYPE_BLOCK, h2b_rev(blockhash))
        response = await self.pool.get(inv_item)
        return response and {
            "block_hash": response.hash(),
            "prev_block_hash": response.previous_block_hash,
            "timestamp": response.timestamp,
            "header_bytes": response.as_blockheader().as_bin(),
            "block_object": response
        }

    async def get_blocks(self, start: str, stop: str, max: int) -> List[Dict]:
        pass

    def add_on_connect_callback(self, callback):
        self._on_connect_callbacks.append(callback)

    async def start(self):
        self.pool.add_on_connected_observer(self.on_connect)
        peers = await utils.dns_bootstrap_servers(self.network)
        _ = [self.pool.add_peer(peer) for peer in peers]
        self.loop.create_task(self.pool.connect())
