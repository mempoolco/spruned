import asyncio
import time

import typing
from pycoin.block import Block

from spruned.application.logging_factory import Logger
from spruned.application.tools import async_delayed_task
from spruned.daemon import exceptions
from spruned.daemon.p2p.p2p_connection import P2PConnection
from spruned.daemon.p2p.p2p_interface import P2PInterface
from spruned.dependencies.pycoinnet.pycoin.InvItem import InvItem
from spruned.repositories.repository import Repository


class MempoolObserver:
    def __init__(self,
                 repository: Repository,
                 p2p_interface: P2PInterface
                 ):
        self.repository = repository
        self.p2p = p2p_interface
        self.loop = asyncio.get_event_loop()
        self.delayer = async_delayed_task
        self.on_transaction_callbacks = []
        self.on_transaction_hash_callbacks = []
        self.on_new_block_callbacks = []

    def add_on_new_block_callback(self, callback):
        self.on_new_block_callbacks.append(callback)

    def add_on_transaction_callback(self, callback):
        self.on_transaction_callbacks.append(callback)

    def add_on_transaction_hash_callback(self, callback):
        self.on_transaction_hash_callbacks.append(callback)

    async def on_block_header(self, block_header: dict, i=0):
        try:
            Logger.mempool.debug('New block request: %s', block_header['block_hash'])
            block_transactions, size = await self.repository.blockchain.get_transactions_by_block_hash(
                block_header['block_hash']
            )
            block_raw_data = (tx['transaction_bytes'] for tx in block_transactions)
            try:
                cached_block = block_transactions and (block_header['header_bytes'] + b''.join(block_raw_data)) or None
                block_object = Block.from_bin(cached_block)
            except:
                Logger.mempool.exception('Failed cache data recovery')
                block_object = None
            if block_object:
                Logger.mempool.debug('Block %s in cache', block_header['block_hash'])
                block = {
                    'block_object': block_object,
                }
            else:
                Logger.mempool.debug('Block %s not in cache, fetching', block_header['block_hash'])
                block = await self.p2p.get_block(block_header['block_hash'])
                if not block:
                    raise exceptions.MissingResponseException
                Logger.mempool.debug(
                    'Block %s not cached, saving', block_header['block_hash']
                )
                block = await self.repository.blockchain.save_block(block)

            Logger.mempool.debug('Block %s, fetch done', block_header['block_hash'])
            block_txids, removed_txids = self.repository.mempool.on_new_block(block['block_object'])
            Logger.mempool.debug(
                'Block %s parsed by mempool repository, removed %s transactions' % (
                    block_header['block_hash'], len(removed_txids)
                )
            )
            block_header.update({"txs": block_txids})
            block.update({"verbose": block_header})

            for callback in self.on_new_block_callbacks:
                self.loop.create_task(callback(block['block_object']))
        except (exceptions.NoPeersException, exceptions.MissingResponseException) as e:
            if i > 10:
                Logger.mempool.debug(
                    'Block fetch for %s failed (will NOT retry)', block_header['block_hash']
                )
                raise
            Logger.mempool.debug(
                'Block fetch for %s failed (will retry)', block_header['block_hash']
            )
            self.loop.create_task(self.delayer(self.on_block_header(block_header, i=i + 1), 10))

    async def on_transaction_hash(self, connection: P2PConnection, item: InvItem):
        txid = str(item.data)
        if self.repository.mempool.add_seen(txid, '{}/{}'.format(connection.hostname, connection.port)):
            await self.p2p.pool.get_from_connection(connection, item)
            return

    async def on_transaction(self, connection: P2PConnection, transaction: typing.Dict):
        txid = str(transaction['tx'].w_id())
        Logger.mempool.debug('New TX %s', txid)
        transaction = {
            "timestamp": int(time.time()),
            "txid": txid,
            "outpoints": ["{}:{}".format(x.previous_hash, x.previous_index) for x in transaction["tx"].txs_in],
            "bytes": transaction['tx'].as_bin(),
            "tx": transaction['tx']
        }
        transaction["size"] = len(transaction["bytes"])
        self.repository.mempool.add_transaction(transaction["txid"], transaction)
        for callback in self.on_transaction_callbacks:
            self.loop.create_task(callback(transaction['tx']))
        for callback in self.on_transaction_hash_callbacks:
            self.loop.create_task(callback(transaction['tx']))
