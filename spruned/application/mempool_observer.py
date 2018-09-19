import asyncio
import time

from spruned.application.logging_factory import Logger

from spruned.application.tools import async_delayed_task

from spruned.daemon import exceptions
from spruned.daemon.bitcoin_p2p.p2p_interface import P2PInterface
from spruned.daemon.bitcoin_p2p.utils import get_block_factory
from spruned.repositories.repository import Repository


class MempoolObserver:
    def __init__(self,
                 repository: Repository,
                 p2p_interface: P2PInterface,
                 async_block_factory=get_block_factory()
                 ):
        self.repository = repository
        self.p2p = p2p_interface
        self.block_factory = async_block_factory
        self.loop = asyncio.get_event_loop()
        self.delayer = async_delayed_task

    async def on_block_header(self, blockheader: dict, i=0):
        try:
            Logger.mempool.debug('New block request: %s', blockheader['block_hash'])
            cached_block = self.repository.blockchain.get_block(blockheader['block_hash'])
            cached_block and Logger.mempool.debug(
                'Block %s in cache', blockheader['block_hash']
            )
            not cached_block and Logger.mempool.debug(
                'Block %s not in cache, fetching', blockheader['block_hash']
            )
            block = cached_block or await self.p2p.get_block(blockheader['block_hash'], timeout=15)
            if not block:
                raise exceptions.MissingResponseException

            block_object = await self.block_factory.get(block['block_bytes'])
            Logger.mempool.debug('Block %s, fetch done', blockheader['block_hash'])
            block_txids, removed_txids = self.repository.mempool.on_new_block(block_object)
            Logger.mempool.debug(
                'Block %s parsed by mempool repository, removed %s transactions' % (
                    blockheader['block_hash'], len(removed_txids)
                )
            )
            blockheader.update({"txs": block_txids})
            block.update({"verbose": blockheader})
            if not cached_block:
                Logger.mempool.debug(
                    'Block %s not cached, saving', blockheader['block_hash']
                )
                self.repository.blockchain.save_block(block)
        except (exceptions.NoPeersException, exceptions.MissingResponseException):
            if i > 10:
                Logger.mempool.debug(
                    'Block fetch for %s failed (will NOT retry)', blockheader['block_hash']
                )
                raise
            Logger.mempool.debug(
                'Block fetch for %s failed (will retry)', blockheader['block_hash']
            )
            self.loop.create_task(self.delayer(self.on_block_header(blockheader, i=i+1), 10))

    async def on_transaction_hash(self, connection, item):
        txid = str(item.data)
        if self.repository.mempool.add_seen(txid, '{}/{}'.format(connection.hostname, connection.port)):
            await self.p2p.pool.get_from_connection(connection, item)
            return

    async def on_transaction(self, connection, item):
        txid = str(item['tx'].w_hash())
        Logger.mempool.debug('New TX %s', txid)
        transaction = {
            "timestamp": int(time.time()),
            "txid": txid,
            "outpoints": ["{}:{}".format(x.previous_hash, x.previous_index) for x in item["tx"].txs_in],
            "bytes": item['tx'].as_bin()
        }
        transaction["size"] = len(transaction["bytes"])
        self.repository.mempool.add_transaction(transaction["txid"], transaction)
