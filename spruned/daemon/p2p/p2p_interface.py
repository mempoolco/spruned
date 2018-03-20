import asyncio
from typing import Dict

import sys

import time
from pycoin.message.InvItem import ITEM_TYPE_BLOCK, InvItem, ITEM_TYPE_MERKLEBLOCK, ITEM_TYPE_TX
from pycoin.serialize import h2b_rev, h2b
from pycoin.tx import Tx

from spruned.daemon.p2p import utils
from spruned.daemon.p2p.p2p_connection import P2PConnectionPool


class P2PInterface:
    def __init__(self, connection_pool: P2PConnectionPool):
        self.pool = connection_pool

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

    async def getrawtransaction(self, txid: str) -> Dict:
        inv_item = InvItem(ITEM_TYPE_TX, h2b(txid))
        response: Tx = await self.pool.get(inv_item)
        return response.as_bin()

    async def get_header(self, blockheight: int) -> Dict:  # pragma: no cover
        pass


async def test():
    from pycoinnet.networks import MAINNET
    peers = await utils.dns_bootstrap_servers(MAINNET)
    pool = P2PConnectionPool(peers=peers, connections=8)
    interface = P2PInterface(pool)
    print(peers)
    loop.create_task(pool.connect())

    c = len(pool.established_connections)
    await asyncio.sleep(1)
    while c < 5:
        print('not ready: %s' % c)
        c = len(pool.established_connections)
        await asyncio.sleep(5)
    print('ready!')
    blockhash = '0000000000000000001f0324001c8acc2a32608275ab3730d41d90d5507391b7'
    while 1:
        now = time.time()
        await asyncio.sleep(1)
        res = await interface.get_block(blockhash)
        if not res:
            continue
        print('Block downloaded in %s' % (time.time() - now))
        print('Block: %s' % res)
        blockhash = str(res['prev_block_hash'])


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test())
