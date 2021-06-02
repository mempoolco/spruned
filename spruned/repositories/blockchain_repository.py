from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum
from functools import partial
from typing import Dict, List

import typing

from spruned.application.tools import blockheader_to_blockhash, deserialize_header
from spruned.services import exceptions as daemon_exceptions  # fixme remove
from spruned.application import exceptions

import asyncio


class DBPrefix(Enum):
    DB_VERSION = 1
    TRANSACTION = 2
    BLOCK_INDEX = 3
    HEADER = 4
    BLOCKHASH_BY_HEIGHT = 5
    BEST_HEIGHT = 6


class BlockchainRepository:
    current_version = 1

    def __init__(self, genesis_block: bytes, session, dbpath):
        self.genesis_block = genesis_block
        self.session = session
        self.dbpath = dbpath
        self._cache = None
        self.loop = asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=64)
        self._best_header = None

    def _ensure_brand_new_db(self, batch_session):
        from spruned.application.database import BRAND_NEW_DB_PLACEHOLDER
        if not self.session.get(BRAND_NEW_DB_PLACEHOLDER):
            raise exceptions.DatabaseInconsistencyException('brand new flag not found')
        batch_session.delete(BRAND_NEW_DB_PLACEHOLDER)

    def initialize(self):
        db_version = self.session.get(self._get_db_key(DBPrefix.DB_VERSION))
        db_version = db_version and int.from_bytes(db_version, 'little')
        if db_version is None:
            batch_session = self.session.write_batch()
            self._ensure_brand_new_db(batch_session)
            self._initialize_genesis_block(batch_session)
            batch_session.put(self._get_db_key(DBPrefix.DB_VERSION), self.current_version.to_bytes(2, 'little'))
            batch_session.write()
        elif db_version != self.current_version:
            raise exceptions.DatabaseInconsistencyException('invalid db_version')
        else:
            self._ensure_genesis_block()

    def _ensure_genesis_block(self):
        key = self._get_db_key(DBPrefix.BLOCKHASH_BY_HEIGHT, int(0).to_bytes(4, 'little'))
        current_genesis_hash = self.session.get(key)
        expected_genesis_hash = blockheader_to_blockhash(self.genesis_block)
        if current_genesis_hash != expected_genesis_hash:
            raise exceptions.DatabaseInconsistencyException('invalid genesis hash stored')

    def _initialize_genesis_block(self, batch_session):
        genesis_block_height = int(0).to_bytes(4, 'little')
        height_key = self._get_db_key(
            DBPrefix.BLOCKHASH_BY_HEIGHT,
            genesis_block_height
        )
        genesis_header = self.genesis_block[:80]
        genesis_hash = blockheader_to_blockhash(genesis_header)
        header_key = self._get_db_key(DBPrefix.HEADER, genesis_hash)
        best_height_key = self._get_db_key(DBPrefix.BEST_HEIGHT)
        batch_session.put(height_key, genesis_hash)
        batch_session.put(header_key, genesis_header + genesis_block_height)
        batch_session.put(best_height_key, genesis_block_height)

    @staticmethod
    def _get_db_key(prefix: DBPrefix, name: bytes = b''):
        assert isinstance(name, bytes)
        return b'%s:%s' % (int.to_bytes(prefix.value, 2, "big"), name)

    def erase(self):
        from spruned.application.database import erase_ldb_storage
        erase_ldb_storage()

    def _save_db_version(self, batch_session):
        batch_session.put(
            self._get_db_key(DBPrefix.DB_VERSION),
            self.current_version.to_bytes(2, 'little')
        )

    def set_cache(self, cache):
        self._cache = cache

    async def save_block(self, block: Dict, batch_session=None) -> Dict:
        return await self.loop.run_in_executor(
            self.executor,
            partial(self._save_block, block, batch_session=batch_session)
        )

    def _save_block(self, block: typing.Dict, batch_session):
        blockhash = block['hash']
        saved_transactions = map(
            lambda transaction: self._save_transaction(
                {
                    'hash': transaction['hash'],
                    'bytes': transaction['bytes']
                },
                blockhash,
                batch_session=batch_session
            ), block['txs']
        )
        self._save_block_index(
            blockhash,
            block['size'],
            saved_transactions,
            batch_session
        )
        return block

    def _save_block_index(
            self, blockhash: bytes,
            blocksize: int,
            transactions: typing.Iterable[typing.Dict],
            batch_session
    ):
        size = blocksize.to_bytes(4, 'little')
        batch_session.put(
            self._get_db_key(DBPrefix.BLOCK_INDEX, blockhash),
            size + b''.join(map(lambda t: t['hash'], transactions))  # fixme argh?
        )

    async def get_block_index(self, blockhash: str):
        return await self.loop.run_in_executor(
            self.executor,
            self._get_block_index,
            bytes.fromhex(blockhash)
        )

    def _get_block_index(self, blockhash: bytes):
        assert isinstance(blockhash, bytes)
        return self.session.get(
            self._get_db_key(DBPrefix.BLOCK_INDEX, blockhash)
        )

    async def save_blocks(self, blocks: typing.Iterable[Dict]) -> List[Dict]:
        return await self.loop.run_in_executor(
            self.executor,
            self._save_blocks,
            blocks
        )

    def _save_blocks(self, blocks: typing.Iterable[Dict]) -> List[Dict]:
        batch_session = self.session.write_batch()
        response = []
        for block in blocks:
            response.append(self._save_block(block, batch_session))
        batch_session.write()
        return response

    def _save_transaction(self, transaction: Dict, block_hash: bytes, batch_session) -> Dict:
        batch_session.put(
            self._get_db_key(DBPrefix.TRANSACTION, transaction['hash']),
            transaction['bytes'] + block_hash  # fixme aaarrrgh!
        )
        return transaction

    async def get_block_size_and_transaction_ids(self, blockhash: str) \
            -> typing.Tuple[typing.Optional[int], typing.Iterable[str]]:
        resp = await self.loop.run_in_executor(
            self.executor,
            self._get_block_size_and_transaction_ids,
            bytes.fromhex(blockhash)
        )
        return resp[0], list(map(lambda txid: txid.hex(), resp[1]))

    def _get_block_size_and_transaction_ids(self, blockhash: bytes) \
            -> typing.Tuple[typing.Optional[int], typing.Iterable[bytes]]:
        block_index = self._get_block_index(blockhash)
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
        return await self.loop.run_in_executor(
            self.executor,
            self._get_transactions_by_block_hash,
            blockhash
        )

    def _get_transactions_by_block_hash(self, blockhash: str) -> (List[Dict], int):
        block_index = self._get_block_index(bytes.fromhex(blockhash))
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
            transaction = self._get_transaction(txid)
            if not transaction:
                raise exceptions.DatabaseInconsistencyException
            transactions.append(transaction)
            i += 32
        return int.from_bytes(block_size, 'little'), transactions

    async def get_transaction(self, txid: str) -> (None, Dict):
        return await self.loop.run_in_executor(
            self.executor,
            self._get_transaction,
            bytes.fromhex(txid)
        )

    def _get_transaction(self, txid: bytes):
        data = self.session.get(
            self._get_db_key(DBPrefix.TRANSACTION, txid)
        )
        if not data:
            return
        return {
            'transaction_bytes': data[:-32],
            'block_hash': data[-32:],
            'txid': txid
        }

    async def _remove_block(self, blockhash: bytes):
        # fixme todo
        block_size, transaction_ids = self._get_block_size_and_transaction_ids(blockhash)
        if any(
            filter(
                lambda r: isinstance(r, Exception),
                await asyncio.gather(
                    *map(
                        lambda txid: self._remove_item(
                            self._get_db_key(DBPrefix.TRANSACTION, txid)
                        ),
                        transaction_ids
                    ),
                    self._remove_item(
                        self._get_db_key(DBPrefix.BLOCK_INDEX, blockhash)
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

    async def save_headers(self, headers: typing.List[typing.Dict]):
        resp = await self.loop.run_in_executor(
            self.executor,
            self._save_headers,
            headers
        )
        return resp

    def _save_headers(self, headers: typing.List[typing.Dict]):
        """
        append only storage, accept only headers subsequent to the existing stored.
        """
        best_header = self._get_best_header(True)
        if best_header['block_hash'] != headers[0]['prev_block_hash']:
            raise exceptions.DatabaseInconsistencyException
        batch_session = self.session.write_batch()
        saved_headers = []
        last_header = None
        for i, header in enumerate(headers):
            assert not i or header['prev_block_hash'] == headers[i-1]['block_hash']
            saved_headers.append(self._save_header(header, batch_session))
            last_header = header
        assert last_header
        self._best_header = last_header
        self._save_best_height(last_header['block_height'], batch_session)
        batch_session.write()
        return saved_headers

    def _save_header(self, header, batch_session):
        header_key = self._get_db_key(DBPrefix.HEADER, bytes.fromhex(header['block_hash']))
        header_height = header['block_height'].to_bytes(4, 'little')
        height_key = self._get_db_key(DBPrefix.BLOCKHASH_BY_HEIGHT, header_height)
        batch_session.put(header_key, header['header_bytes'] + header_height)
        batch_session.put(height_key, bytes.fromhex(header['block_hash']))
        return header

    async def get_header(self, blockhash: str, verbose=True) -> typing.Dict:
        return await self.loop.run_in_executor(
            self.executor,
            self._get_header,
            bytes.fromhex(blockhash),
            verbose
        )

    def _get_header(self, blockhash: bytes, verbose: bool) -> typing.Dict:
        key = self._get_db_key(DBPrefix.HEADER, blockhash)
        data = self.session.get(key)
        if not data:
            raise exceptions.DatabaseDataNotFoundException
        if len(data) != 84:
            raise exceptions.DatabaseInconsistencyException
        header = data[:80]
        if not verbose:
            return {'header_bytes': header}

        header_height = int.from_bytes(data[80:], 'little')
        h_dict = deserialize_header(header, fmt='hex')
        h_dict['block_height'] = header_height
        h_dict['block_hash'] = h_dict.pop('hash')
        h_dict['header_bytes'] = header
        next_block_hash = self._get_block_hash(int.to_bytes(header_height + 1, 4, 'little'))
        if next_block_hash:
            h_dict['next_block_hash'] = next_block_hash and next_block_hash.hex()
        return h_dict

    def get_headers(self, start_hash: str):
        return self.loop.run_in_executor(
            self.executor,
            self._get_headers,
            bytes.fromhex(start_hash)
        )

    def _get_headers(self, start_hash: bytes) -> typing.List[typing.Dict]:
        headers = []
        header = self._get_header(start_hash, verbose=True)
        if not header:
            raise exceptions.DatabaseInconsistencyException
        headers.append(header)
        cur_hash = header['block_hash']
        cur_height = header['block_height']
        while 1:
            n_header = self._get_header_at_height((cur_height + 1).to_bytes(4, 'little'), True)
            if not n_header:
                break
            assert cur_hash == n_header['prev_block_hash'], (cur_hash, n_header)
            assert n_header['block_height'] == cur_height + 1
            cur_hash = n_header['block_hash']
            cur_height = n_header['block_height']
            headers.append(n_header)
        return headers

    async def get_header_at_height(self, height: int, verbose=True):
        return await self.loop.run_in_executor(
            self.executor,
            self._get_header_at_height,
            height.to_bytes(4, 'little'),
            verbose
        )

    def _get_header_at_height(self, height: bytes, verbose: bool) -> typing.Dict:
        height_key = self._get_db_key(DBPrefix.BLOCKHASH_BY_HEIGHT, height)
        header_hash = self.session.get(height_key)
        if header_hash:
            return self._get_header(header_hash, verbose)

    def remove_headers(self, start_hash: str):
        raise NotImplementedError

    async def get_best_height(self) -> int:
        best_height = await self.loop.run_in_executor(
            self.executor,
            self._get_best_height
        )
        return best_height and int.from_bytes(best_height, 'little')

    def _get_best_height(self) -> bytes:
        key = self._get_db_key(DBPrefix.BEST_HEIGHT)
        best_height = self.session.get(key)
        return best_height

    async def get_best_header(self, verbose=True) -> typing.Dict:
        if not self._best_header:
            self._best_header = await self.loop.run_in_executor(
                self.executor,
                self._get_best_header,
                verbose
            )
        return self._best_header

    def _get_best_header(self, verbose):
        best_height = self._get_best_height()
        return self._get_header_at_height(best_height, verbose)

    def _save_best_height(self, height: int, batch_session):
        key = self._get_db_key(DBPrefix.BEST_HEIGHT)
        batch_session.put(key, height.to_bytes(4, 'little'))

        return height

    async def get_block_hash(self, height: int):
        resp = (await self.loop.run_in_executor(
            self.executor,
            self._get_block_hash,
            height.to_bytes(4, 'little')
        ))
        return resp and resp.hex()

    def _get_block_hash(self, height: bytes):
        key = self._get_db_key(DBPrefix.BLOCKHASH_BY_HEIGHT, height)
        block_hash = self.session.get(key)
        return block_hash and block_hash

    async def get_best_block_hash(self):
        return (await self.loop.run_in_executor(
            self.executor,
            self._get_best_block_hash
        )).hex()

    def _get_best_block_hash(self):
        best_height = self._get_best_height()
        return self._get_block_hash(best_height)

    async def get_block_hashes_in_range(self, start_from_height: int, limit: int):
        return await self.loop.run_in_executor(
            self.executor,
            self._get_block_hashes_in_range,
            start_from_height,
            limit,
            True
        )

    def _get_block_hashes_in_range(
            self, start_from_height, limit, serialize: bool
    ) -> typing.Iterable[typing.Optional[str]]:
        def fn(_h):
            res = self._get_block_hash(int.to_bytes(_h, 4, 'little'))
            if res and serialize:
                return res.hex()
            return res

        return list(map(fn, range(start_from_height, start_from_height + limit)))
