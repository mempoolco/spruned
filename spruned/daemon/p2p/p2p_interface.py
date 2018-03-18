import asyncio
from typing import Dict
from pycoin.message.InvItem import ITEM_TYPE_BLOCK, InvItem, ITEM_TYPE_MERKLEBLOCK, ITEM_TYPE_TX
from pycoin.serialize import h2b_rev, h2b
from pycoin.tx import Tx
from spruned.daemon.p2p.p2p_connection import P2PConnectionPool


class P2PInterface:
    def __init__(self, connection_pool: P2PConnectionPool):
        self.pool = connection_pool

    async def get_block(self, blockhash: str) -> Dict:
        inv_item = InvItem(ITEM_TYPE_BLOCK, h2b_rev(blockhash))
        response = await self.pool.get(inv_item)
        return {
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

    async def get_header(self, blockhash: str) -> Dict:
        inv_item = InvItem(ITEM_TYPE_MERKLEBLOCK, h2b_rev(blockhash))
        response = await self.pool.get(inv_item)
        return {
            "block_hash": response.hash(),
            "prev_block_hash": response.previous_block_hash,
            "timestamp": response.timestamp,
            "header_bytes": response.as_bin(),
        }


async def test(l):
    pool = P2PConnectionPool()
    l.create_task(pool.connect())
    await asyncio.sleep(10)
    while 1:
        if pool.available:
            await asyncio.sleep(10)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(test(loop))
