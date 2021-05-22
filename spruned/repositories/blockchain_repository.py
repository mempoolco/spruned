import binascii
from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum
from functools import partial
from typing import Dict, List

import typing

from fifolock import FifoLock
from pycoin.block import Block

from spruned.application.logging_factory import Logger
from spruned.daemon import exceptions as daemon_exceptions  # fixme remove
from spruned.application import exceptions

from spruned.repositories.abstracts import BlockchainRepositoryAbstract
import asyncio


class Read(asyncio.Future):
    @staticmethod
    def is_compatible(holds):
        return not holds[Write]


class Write(asyncio.Future):
    @staticmethod
    def is_compatible(holds):
        return not holds[Read] and not holds[Write]


class DBPrefix(Enum):
    TRANSACTION_PREFIX = 0
    BLOCK_INDEX_PREFIX = 1
    DB_VERSION = 4


class BlockchainRepository(BlockchainRepositoryAbstract):
    current_version = 4

    def __init__(self, session, storage_name, dbpath):
        self.storage_name = storage_name
        self.session = session
        self.dbpath = dbpath
        self._cache = None
        self.volatile = {}
        self.loop = asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=8)
        self.lock = FifoLock()

    @staticmethod
    def _get_key(name: (bytes, str), prefix: (bytes, DBPrefix)):  # fixme
        name = isinstance(name, str) and binascii.unhexlify(name.encode()) or name
        return b'%s.%s' % (
            (prefix if isinstance(prefix, bytes) else int.to_bytes(prefix.value, 2, "big")), name
        )

    async def erase(self):
        from spruned.application.database import erase_ldb_storage
        erase_ldb_storage()
        await self._save_db_version()

    async def _save_db_version(self):
        session = self.session.write_batch()
        await self.loop.run_in_executor(
            self.executor,
            session.put,
            self._get_key(self.storage_name, DBPrefix.DB_VERSION),
            self.current_version.to_bytes(2, 'little')
        )

    async def get_db_version(self):
        v = await self.loop.run_in_executor(
            self.executor,
            self.session.get,
            self._get_key(self.storage_name, DBPrefix.DB_VERSION)
        )
        return v and int.from_bytes(v, 'little')

    def set_cache(self, cache):
        self._cache = cache

    async def save_block(self, block: Dict, tracker=None, batch_session=None) -> Dict:
        return await self.loop.run_in_executor(
            self.executor,
            partial(self._save_block, block, tracker, batch_session=batch_session)
        )

    def _save_block(self, block, tracker, batch_session=None):
        block['size'] = len(block['block_bytes'])
        block['block_object'] = block.get('block_object', Block.from_bin(block.get('block_bytes')))

        blockhash = binascii.unhexlify(block['block_hash'].encode())
        batch_session = batch_session or self.session.write_batch()
        saved_transactions = (
            self._save_transaction(
                {
                    'txid': transaction.id(),
                    'transaction_bytes': transaction.as_bin(),
                    'block_hash': blockhash
                },
                batch_session=batch_session
            ) for transaction in block['block_object'].txs
        )
        transaction_ids = list(map(
            lambda t: t['txid'],
            filter(lambda t: isinstance(t, dict), saved_transactions)
        ))
        if len(transaction_ids) != len(block['block_object'].txs):
            raise exceptions.DatabaseInconsistencyException
        self._save_block_index(
            blockhash,
            block['size'],
            map(lambda txid: bytes.fromhex(txid), transaction_ids),
            batch_session
        )
        tracker and tracker.track(
            self._get_key(block['block_hash'], prefix=DBPrefix.BLOCK_INDEX_PREFIX),
            len(block['block_bytes'])
        )
        batch_session.write()
        return block

    def _save_block_index(
            self, blockhash: bytes, blocksize: int, txids: typing.Iterable[bytes], batch_session
    ):
        key = self._get_key(blockhash, prefix=DBPrefix.BLOCK_INDEX_PREFIX)
        size = blocksize.to_bytes(4, 'little')
        batch_session.put(
            self.storage_name + b'.' + key,
            size + b''.join(txids)
        )

    async def get_block_index(self, blockhash: str):
        key = self._get_key(blockhash, prefix=DBPrefix.BLOCK_INDEX_PREFIX)
        return await self.loop.run_in_executor(
            self.executor,
            self.session.get,
            self.storage_name + b'.' + key
        )

    async def save_blocks(self, *blocks: Dict) -> List[Dict]:
        resp = list(
            await asyncio.gather(
                *map(
                    lambda b: self.loop.run_in_executor(
                        self.executor,
                        self.save_block,
                        b
                    ),
                    blocks
                ),
                return_exceptions=True
            )
        )
        if any(filter(lambda r: isinstance(r, Exception), resp)):
            raise exceptions.DatabaseInconsistencyException
        return resp

    def _save_transaction(self, transaction: Dict, batch_session) -> Dict:
        data = transaction['transaction_bytes'] + transaction['block_hash']
        key = self._get_key(transaction['txid'], prefix=DBPrefix.TRANSACTION_PREFIX)
        batch_session.put(
            self.storage_name + b'.' + key,
            data
        )
        return transaction

    async def get_txids_by_block_hash(self, blockhash: str) -> (List[str], int):
        block_index = await self.get_block_index(blockhash)
        if not block_index:
            return [], None
        i = 0
        txids = []
        size = block_index[:4]
        block_index = block_index[4:]
        while 1:
            txid = binascii.hexlify(block_index[i:i + 32]).decode()
            if not txid:
                if i != len(block_index):
                    raise daemon_exceptions.BrokenDataException
                break
            txids.append(txid)
            i += 32
        return txids, int.from_bytes(size, 'little')

    async def get_transactions_by_block_hash(self, blockhash: str) -> (List[Dict], int):
        block_index = await self.get_block_index(blockhash)
        if not block_index:
            return [], None
        i = 0
        size = block_index[:4]
        block_index = block_index[4:]
        transactions = []
        while 1:
            txid = block_index[i:i+32]
            if not txid:
                break
            transaction = await self.get_transaction(txid)
            if not transaction:
                if transactions:
                    Logger.repository.warning('Corrupted storage for blockhash %s, deleting' % blockhash)
                    await self.remove_block(blockhash)
                    return [], None
                break
            transactions.append(transaction)
            i += 32
        return transactions, int.from_bytes(size, 'little')

    async def get_transaction(self, txid: (bytes, str)) -> (None, Dict):
        key = self._get_key(txid, prefix=DBPrefix.TRANSACTION_PREFIX)
        data = self.loop.run_in_executor(
            self.executor,
            self.session.get,
            self.storage_name + b'.' + key
        )
        if not data:
            return
        return {
            'transaction_bytes': data[:-32],
            'block_hash': data[-32:],
            'txid': txid
        }

    async def remove_block(self, blockhash: str):
        txids, size = await self.get_txids_by_block_hash(blockhash)
        if any(
            filter(
                lambda r: isinstance(r, Exception),
                await asyncio.gather(
                    *map(
                        lambda txid: self._remove_item(
                            self._get_key(txid, prefix=DBPrefix.TRANSACTION_PREFIX)
                        ),
                        txids
                    ),
                    self._remove_item(
                        self._get_key(blockhash, prefix=DBPrefix.BLOCK_INDEX_PREFIX)
                    ),
                    return_exceptions=True
                )
            )
        ):
            raise exceptions.DatabaseInconsistencyException

    async def _remove_item(self, key):
        await self.loop.run_in_executor(
            self.executor,
            self.session.delete,
            self.storage_name + b'.' + key
        )

