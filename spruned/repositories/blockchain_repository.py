import binascii
from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum
from functools import partial
from typing import Dict, List

import typing
from fifolock import FifoLock
from pycoin.block import Block

from spruned.application.tools import blockheader_to_blockhash, serialize_header, deserialize_header
from spruned.daemon import exceptions as daemon_exceptions  # fixme remove
from spruned.application import exceptions

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
    DB_VERSION = 1
    TRANSACTION = 2
    BLOCK_INDEX = 3
    HEADER = 4
    BLOCKHASH_BY_HEIGHT = 5
    BEST_HEIGHT = 6


class BlockchainRepository:
    current_version = 1

    def __init__(self, network_rules, session, dbpath):
        self.network_rules = network_rules
        self.session = session
        self.dbpath = dbpath
        self._cache = None
        self.loop = asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=64)
        self.lock = FifoLock()

    @property
    def genesis_block(self):
        return bytes.fromhex(self.network_rules['genesis_block'])

    def _ensure_brand_new_db(self, batch_session):
        from spruned.application.database import BRAND_NEW_DB_PLACEHOLDER
        if not self.session.get(BRAND_NEW_DB_PLACEHOLDER):
            raise exceptions.DatabaseInconsistencyException('brand new flag not found')
        batch_session.delete(BRAND_NEW_DB_PLACEHOLDER)

    def initialize(self):
        db_version = self.session.get(self.get_db_key(DBPrefix.DB_VERSION))
        db_version = db_version and int.from_bytes(db_version, 'little')
        if db_version is None:
            batch_session = self.session.write_batch()
            self._ensure_brand_new_db(batch_session)
            self._initialize_genesis_block(batch_session)
            batch_session.put(self.get_db_key(DBPrefix.DB_VERSION), self.current_version.to_bytes(2, 'little'))
            batch_session.write()
        elif db_version != self.current_version:
            raise exceptions.DatabaseInconsistencyException('invalid db_version')
        else:
            self._ensure_genesis_block()

    def _ensure_genesis_block(self):
        key = self.get_db_key(DBPrefix.BLOCKHASH_BY_HEIGHT, int(0).to_bytes(4, 'little'))
        current_genesis_hash = self.session.get(key)
        expected_genesis_hash = blockheader_to_blockhash(self.genesis_block)
        if current_genesis_hash != expected_genesis_hash:
            raise exceptions.DatabaseInconsistencyException('invalid genesis hash stored')

    def _initialize_genesis_block(self, batch_session):
        genesis_block_height = int(0).to_bytes(4, 'little')
        height_key = self.get_db_key(
            DBPrefix.BLOCKHASH_BY_HEIGHT,
            genesis_block_height
        )
        genesis_header = self.genesis_block[:80]
        genesis_hash = blockheader_to_blockhash(genesis_header)
        header_key = self.get_db_key(DBPrefix.HEADER, genesis_hash)
        best_height_key = self.get_db_key(DBPrefix.BEST_HEIGHT)
        batch_session.put(height_key, genesis_hash)
        batch_session.put(header_key, genesis_header + genesis_block_height)
        batch_session.put(best_height_key, genesis_block_height)

    @staticmethod
    def get_db_key(prefix: DBPrefix, name: bytes = b''):
        assert isinstance(name, bytes)
        return b'%s:%s' % (int.to_bytes(prefix.value, 2, "big"), name)

    def erase(self):
        from spruned.application.database import erase_ldb_storage
        erase_ldb_storage()

    def _save_db_version(self, batch_session):
        batch_session.put(
            self.get_db_key(DBPrefix.DB_VERSION),
            self.current_version.to_bytes(2, 'little')
        )

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
            self.get_db_key(DBPrefix.BLOCK_INDEX_PREFIX, blockhash),
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
            self.get_db_key(DBPrefix.BLOCK_INDEX_PREFIX, blockhash)
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
            self.get_db_key(DBPrefix.TRANSACTION_PREFIX, transaction['txid']),
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
            self.get_db_key(DBPrefix.TRANSACTION_PREFIX, txid)
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
                            self.get_db_key(DBPrefix.TRANSACTION_PREFIX, txid)
                        ),
                        transaction_ids
                    ),
                    self._remove_item(
                        self.get_db_key(DBPrefix.BLOCK_INDEX_PREFIX, blockhash)
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

    async def save_headers(self, headers):
        resp = await self.loop.run_in_executor(self.executor, self._save_headers, headers)
        return resp

    def _save_headers(self, headers: typing.List[typing.Dict]):
        """
        append only storage, accept only headers subsequent to the existing stored.
        """
        best_header = self.get_best_header()
        try:
            if best_header['block_hash'] != headers[0]['prev_block_hash']:
                raise exceptions.DatabaseInconsistencyException
        except:
            raise
        batch_session = self.session.write_batch()
        saved_headers = []
        last_header = None
        for i, header in enumerate(headers):
            assert not i or header['prev_block_hash'] == headers[i-1]['block_hash']
            saved_headers.append(self._save_header(header, batch_session))
            last_header = header
        assert last_header
        self._save_best_height(last_header['block_height'], batch_session)
        batch_session.write()
        return saved_headers

    def _save_header(self, header, batch_session):
        header_key = self.get_db_key(DBPrefix.HEADER, bytes.fromhex(header['block_hash']))
        header_height = header['block_height'].to_bytes(4, 'little')
        height_key = self.get_db_key(DBPrefix.BLOCKHASH_BY_HEIGHT, header_height)
        batch_session.put(header_key, header['header_bytes'] + header_height)
        batch_session.put(height_key, bytes.fromhex(header['block_hash']))
        return header

    def get_header(self, blockhash: str) -> typing.Dict:
        return self._get_header(bytes.fromhex(blockhash))

    def _get_header(self, blockhash: bytes) -> typing.Dict:
        key = self.get_db_key(DBPrefix.HEADER, blockhash)
        data = self.session.get(key)
        if not data:
            raise exceptions.DatabaseDataNotFoundException
        if len(data) != 84:
            raise exceptions.DatabaseInconsistencyException
        header = data[:80]
        header_height = int.from_bytes(data[80:], 'little')
        h_dict = deserialize_header(header, fmt='hex')
        h_dict['block_height'] = header_height
        h_dict['block_hash'] = h_dict.pop('hash')
        return h_dict

    def get_headers(self, start_hash: str, limit=6) -> typing.List[typing.Dict]:
        headers = []
        assert limit <= 3000, 'absurdly high limit'
        header = self.get_header(start_hash)
        if not header:
            raise exceptions.DatabaseInconsistencyException
        headers.append(header)
        cur_hash = header['block_hash']
        for height in range(header['block_height'] + 1, header['block_height'] + limit):
            n_header = self.get_header_at_height(height)
            if not n_header:
                break
            assert cur_hash == n_header['prev_block_hash']
            headers.append(header)
        return headers

    def get_header_at_height(self, height: int) -> typing.Dict:
        height_key = self.get_db_key(DBPrefix.BLOCKHASH_BY_HEIGHT, height.to_bytes(4, 'little'))
        header_hash = self.session.get(height_key)
        if header_hash:
            return self._get_header(header_hash)

    def remove_headers(self, start_hash: str):
        raise NotImplementedError

    def get_best_height(self) -> int:
        key = self.get_db_key(DBPrefix.BEST_HEIGHT)
        best_height = self.session.get(key)
        assert isinstance(best_height, bytes), best_height
        best_height = int.from_bytes(best_height, 'little')
        return best_height

    def get_best_header(self) -> typing.Dict:
        best_height = self.get_best_height()
        return self.get_header_at_height(best_height)

    def _save_best_height(self, height: int, batch_session):
        key = self.get_db_key(DBPrefix.BEST_HEIGHT)
        batch_session.put(key, height.to_bytes(4, 'little'))
        return height

    async def get_block_hash(self, height: int):
        key = self.get_db_key(DBPrefix.BLOCKHASH_BY_HEIGHT, height.to_bytes(4, 'little'))
        block_hash = self.session.get(key)
        return block_hash and block_hash.hex()
