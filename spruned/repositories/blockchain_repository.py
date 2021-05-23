import binascii
from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum
from functools import partial
from typing import Dict, List

import typing
from fifolock import FifoLock
from pycoin.block import Block

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
    TRANSACTION_PREFIX = 1
    BLOCK_INDEX_PREFIX = 2
    HEADERS_PREFIX = 3

    DB_VERSION = 99


class BlockchainRepository(BlockchainRepositoryAbstract):
    current_version = 5

    def __init__(self, session, dbpath):
        self.session = session
        self.dbpath = dbpath
        self._cache = None
        self.loop = asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=64)
        self.lock = FifoLock()

    @staticmethod
    def _get_key(prefix: DBPrefix, name: bytes = b''):
        assert isinstance(name, bytes)
        return b'%s:%s' % (int.to_bytes(prefix.value, 2, "big"), name)

    async def erase(self):
        from spruned.application.database import erase_ldb_storage
        erase_ldb_storage()
        await self._save_db_version()

    async def _save_db_version(self):
        session = self.session.write_batch()
        await self.loop.run_in_executor(
            self.executor,
            session.put,
            self._get_key(DBPrefix.DB_VERSION),
            self.current_version.to_bytes(2, 'little')
        )

    async def get_db_version(self):
        v = await self.loop.run_in_executor(
            self.executor,
            self.session.get,
            self._get_key(DBPrefix.DB_VERSION)
        )
        return v and int.from_bytes(v, 'little')

    def set_cache(self, cache):
        self._cache = cache

    async def save_block(self, block: Dict, batch_session=None) -> Dict:
        return await self.loop.run_in_executor(
            self.executor,
            partial(self._save_block, block, batch_session=batch_session)
        )

    def _save_block(self, block, batch_session=None):
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
        batch_session.write()
        return block

    def _save_block_index(
            self, blockhash: bytes, blocksize: int, transaction_ids: typing.Iterable[bytes], batch_session
    ):
        size = blocksize.to_bytes(4, 'little')
        batch_session.put(
            self._get_key(DBPrefix.BLOCK_INDEX_PREFIX, blockhash),
            size + b''.join(transaction_ids)
        )

    async def get_block_index(self, blockhash: str):
        blockhash = bytes.fromhex(blockhash)
        return await self._get_block_index(blockhash)

    async def _get_block_index(self, blockhash: bytes):
        assert isinstance(blockhash, bytes)
        return await self.loop.run_in_executor(
            self.executor,
            self.session.get,
            self._get_key(DBPrefix.BLOCK_INDEX_PREFIX, blockhash)
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
        batch_session.put(
            self._get_key(DBPrefix.TRANSACTION_PREFIX, transaction['txid']),
            transaction['transaction_bytes'] + transaction['block_hash']
        )
        return transaction

    async def get_block_size_and_transaction_ids(self, blockhash: str) \
            -> typing.Tuple[typing.Optional[int], typing.Iterable[str]]:
        blockhash = bytes.fromhex(blockhash)
        resp = await self._get_block_size_and_transaction_ids(blockhash)
        return resp[0], map(lambda txid: txid.hex(), resp[1])

    async def _get_block_size_and_transaction_ids(self, blockhash: bytes) \
            -> typing.Tuple[typing.Optional[int], typing.Iterable[bytes]]:
        block_index = await self._get_block_index(blockhash)
        if not block_index:
            return None, ()
        i = 0
        txids = []
        size = block_index[:4]
        block_index = block_index[4:]
        while 1:
            txid = block_index[i:i + 32]
            if not txid:
                if i != len(block_index):
                    raise daemon_exceptions.BrokenDataException
                break
            txids.append(txid)
            i += 32
        return int.from_bytes(size, 'little'), txids

    async def get_transactions_by_block_hash(self, blockhash: str) -> (List[Dict], int):
        block_index = await self.get_block_index(blockhash)
        if not block_index:
            return None, []
        i = 0
        block_size = block_index[:4]
        block_index = block_index[4:]
        transactions = []
        while 1:
            txid = block_index[i:i+32]
            if not txid:
                break
            transaction = await self._get_transaction(txid)
            if not transaction:
                raise exceptions.DatabaseInconsistencyException
            transactions.append(transaction)
            i += 32
        return int.from_bytes(block_size, 'little'), transactions

    async def get_transaction(self, txid: str) -> (None, Dict):
        return await self._get_transaction(bytes.fromhex(txid))

    async def _get_transaction(self, txid: bytes):
        data = self.loop.run_in_executor(
            self.executor,
            self.session.get,
            self._get_key(DBPrefix.TRANSACTION_PREFIX, txid)
        )
        if not data:
            return
        return {
            'transaction_bytes': data[:-32],
            'block_hash': data[-32:],
            'txid': txid
        }

    async def _remove_block(self, blockhash: bytes):
        block_size, transaction_ids = await self._get_block_size_and_transaction_ids(blockhash)
        if any(
            filter(
                lambda r: isinstance(r, Exception),
                await asyncio.gather(
                    *map(
                        lambda txid: self._remove_item(
                            self._get_key(DBPrefix.TRANSACTION_PREFIX, txid)
                        ),
                        transaction_ids
                    ),
                    self._remove_item(
                        self._get_key(DBPrefix.BLOCK_INDEX_PREFIX, blockhash)
                    ),
                    return_exceptions=True
                )
            )
        ):
            raise exceptions.DatabaseInconsistencyException

    async def _remove_item(self, key: bytes):
        await self.loop.run_in_executor(
            self.executor, self.session.delete, key
        )
