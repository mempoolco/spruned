import asyncio
import time
from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum

import typing
import plyvel

from spruned.application import exceptions
from spruned.application.logging_factory import Logger
from spruned.application.tools import blockheader_to_blockhash
from spruned.repositories.blocks_diskdb import BlocksDiskDB
from spruned.repositories.repository_types import Block, BlockHeader, INT4_MAX


class DBPrefix(Enum):
    DB_VERSION = 1
    BLOCKS_INDEX = 2
    HEADERS_INDEX = 3
    BLOCKHASH_BY_HEIGHT = 4
    BEST_HEIGHT = 5
    LOCAL_CHAIN_HEIGHT = 7


class BlockchainRepository:
    CURRENT_VERSION = 2

    def __init__(
        self,
        leveldb: plyvel.DB,
        diskdb: BlocksDiskDB
    ):
        self.leveldb = leveldb
        self.loop = asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=64)
        self._best_header = None
        self._local_chain_height = None
        self._disk_db = diskdb
        self._save_blocks_lock = asyncio.Lock()

    @property
    def local_chain_height(self):
        if self._local_chain_height is None:
            height = self.leveldb.get(
                self._get_db_key(DBPrefix.LOCAL_CHAIN_HEIGHT)
            )
            self._local_chain_height = height and int.from_bytes(height, 'little')
        return self._local_chain_height

    def _ensure_brand_new_db(self, batch_session: plyvel.DB):
        from spruned.application.database import BRAND_NEW_DB_PLACEHOLDER
        if not self.leveldb.get(BRAND_NEW_DB_PLACEHOLDER):
            raise exceptions.DatabaseInconsistencyException('brand new flag not found')
        batch_session.delete(BRAND_NEW_DB_PLACEHOLDER)

    async def initialize(self, genesis_block: Block):
        db_version = self.leveldb.get(self._get_db_key(DBPrefix.DB_VERSION))
        db_version = db_version and int.from_bytes(db_version, 'little')
        if db_version is None:
            return await self._save_genesis_block(genesis_block)
        elif db_version != self.CURRENT_VERSION:
            raise exceptions.DatabaseInconsistencyException('invalid db_version')
        else:
            return await self._ensure_genesis_block(genesis_block)

    async def _save_genesis_block(self, genesis_block: Block):
        assert isinstance(genesis_block, Block)
        batch_session = self.leveldb.write_batch()
        self._ensure_brand_new_db(batch_session)
        genesis_block_height = int(0).to_bytes(4, 'little')
        genesis_header = genesis_block.data[:80]
        genesis_hash = blockheader_to_blockhash(genesis_header)
        batch_session.put(
            self._get_db_key(DBPrefix.BLOCKHASH_BY_HEIGHT, genesis_block_height),
            genesis_hash
        )
        batch_session.put(
            self._get_db_key(DBPrefix.HEADERS_INDEX, genesis_hash),
            genesis_header + genesis_block_height
        )
        batch_session.put(
            self._get_db_key(DBPrefix.BEST_HEIGHT), genesis_block_height
        )
        batch_session.put(
            self._get_db_key(DBPrefix.LOCAL_CHAIN_HEIGHT), genesis_block_height
        )
        batch_session.put(
            self._get_db_key(DBPrefix.BLOCKS_INDEX, genesis_hash),
            len(genesis_block.data).to_bytes(4, 'little')
        )
        self._disk_db.add(genesis_block)
        batch_session.put(
            self._get_db_key(DBPrefix.DB_VERSION),
            self.CURRENT_VERSION.to_bytes(2, 'little')
        )
        batch_session.write()
        return genesis_block

    async def _ensure_genesis_block(self, genesis_block: Block):
        key = self._get_db_key(DBPrefix.BLOCKHASH_BY_HEIGHT, int(0).to_bytes(4, 'little'))
        current_genesis_hash = self.leveldb.get(key)
        expected_genesis_hash = blockheader_to_blockhash(genesis_block.data)
        if current_genesis_hash != expected_genesis_hash:
            raise exceptions.DatabaseInconsistencyException('invalid genesis hash stored')
        block_len = self.leveldb.get(
            self._get_db_key(DBPrefix.BLOCKS_INDEX, genesis_block.hash)
        )
        block_len = block_len and int.from_bytes(block_len, 'little')
        block_bytes = self._disk_db.get_block(genesis_block.hash) or b''
        if block_len != len(block_bytes):
            raise exceptions.DatabaseInconsistencyException('blocks storage inconsistency')
        if not block_bytes or blockheader_to_blockhash(block_bytes) != genesis_block.hash:
            raise exceptions.DatabaseInconsistencyException('inconsistency db exception on hash')
        return genesis_block

    @staticmethod
    def _get_db_key(prefix: DBPrefix, name: bytes = b''):
        assert isinstance(name, bytes)
        return b'%s:%s' % (int.to_bytes(prefix.value, 2, "big"), name)

    async def save_headers(self, headers: typing.List[BlockHeader]):
        resp = await self.loop.run_in_executor(
            self.executor,
            self._save_headers,
            headers
        )
        return resp

    def _save_headers(self, headers: typing.List[BlockHeader]) -> typing.List[BlockHeader]:
        """
        append only storage, accept only headers subsequent to the existing stored.
        """
        best_header = self._get_best_header()
        if best_header.hash != headers[0].prev_block_hash:
            raise exceptions.DatabaseInconsistencyException('hash')
        if best_header.height != headers[0].height - 1:
            raise exceptions.DatabaseInconsistencyException('height')
        batch_session = self.leveldb.write_batch()
        saved_headers = []
        last_header = None
        for header in headers:
            saved_headers.append(
                self._save_header(header, batch_session)
            )
            last_header = header
        assert last_header
        self._best_header = last_header
        self._save_best_height(last_header.height, batch_session)
        batch_session.write()
        return saved_headers

    def _save_header(self, header: BlockHeader, batch_session: plyvel.DB) -> BlockHeader:
        assert header.height
        height = int(header.height).to_bytes(4, 'little')
        batch_session.put(
            self._get_db_key(DBPrefix.HEADERS_INDEX, header.hash),
            header.data + height
        )
        batch_session.put(
            self._get_db_key(DBPrefix.BLOCKHASH_BY_HEIGHT, header.height.to_bytes(4, 'little')),
            header.hash
        )
        return header

    async def get_header(self, blockhash: bytes) -> typing.Optional[BlockHeader]:
        return await self.loop.run_in_executor(
            self.executor,
            self._get_header,
            blockhash
        )

    def _get_header(self, blockhash: bytes) -> typing.Optional[BlockHeader]:
        key = self._get_db_key(DBPrefix.HEADERS_INDEX, blockhash)
        data = self.leveldb.get(key)
        if not data:
            return
        if len(data) not in (84,):
            raise exceptions.DatabaseInconsistencyException
        header = data[:80]
        height = int.from_bytes(data[80:], 'little')
        return BlockHeader(
            data=header,
            height=height,
            hash=blockhash
        )

    def get_headers(self, start_hash: bytes, stop_hash: typing.Optional[bytes] = None):
        return self.loop.run_in_executor(
            self.executor,
            self._get_headers,
            start_hash,
            stop_hash
        )

    def _get_headers(self, start_hash: bytes, stop_hash: typing.Optional[bytes]) -> typing.List[BlockHeader]:
        headers = []
        header = self._get_header(start_hash)
        if not header:
            raise exceptions.DatabaseInconsistencyException
        headers.append(header)
        cur_hash = header.hash
        cur_height = header.height
        while 1:
            n_header = self._get_header_at_height(
                (cur_height + 1).to_bytes(4, 'little')
            )
            if not n_header:
                break
            assert cur_hash == n_header.prev_block_hash, (cur_hash, n_header.hash, n_header.height)
            assert n_header.height == cur_height + 1
            cur_hash = n_header.hash
            cur_height = n_header.height
            headers.append(n_header)
            if n_header.hash == stop_hash:
                break
        return headers

    async def get_header_at_height(self, height: int) -> BlockHeader:
        return await self.loop.run_in_executor(
            self.executor,
            self._get_header_at_height,
            height.to_bytes(4, 'little')
        )

    def _get_header_at_height(self, height: bytes) -> BlockHeader:
        height_key = self._get_db_key(DBPrefix.BLOCKHASH_BY_HEIGHT, height)
        header_hash = self.leveldb.get(height_key)
        if header_hash:
            return self._get_header(header_hash)

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
        best_height = self.leveldb.get(key)
        return best_height

    async def get_best_header(self) -> BlockHeader:
        if not self._best_header:
            self._best_header = await self.loop.run_in_executor(
                self.executor,
                self._get_best_header
            )
        return self._best_header

    def _get_best_header(self):
        best_height = self._get_best_height()
        return self._get_header_at_height(best_height)

    def _save_best_height(self, height: int, batch_session: plyvel.DB):
        """
        Save the best HEADER height.
        """
        key = self._get_db_key(DBPrefix.BEST_HEIGHT)
        batch_session.put(key, height.to_bytes(4, 'little'))

        return height

    async def get_block_hash(self, height: int) -> typing.Optional[bytes]:
        resp = (
            await self.loop.run_in_executor(
                self.executor,
                self._get_block_hash,
                height.to_bytes(4, 'little')
            )
        )
        return resp

    def _get_block_hash(self, height: bytes) -> typing.Optional[bytes]:
        key = self._get_db_key(DBPrefix.BLOCKHASH_BY_HEIGHT, height)
        block_hash = self.leveldb.get(key)
        return block_hash

    async def get_best_block_hash(self) -> bytes:
        return (
            await self.loop.run_in_executor(
                self.executor,
                self._get_best_block_hash
            )
        )

    def _get_best_block_hash(self):
        best_height = self._get_best_height()
        return self._get_block_hash(best_height)

    async def get_block_hashes_in_range(self, start_from_height: int, limit: int) -> typing.List[bytes]:
        return await self.loop.run_in_executor(
            self.executor,
            self._get_block_hashes_in_range,
            start_from_height,
            limit,
            True
        )

    def _get_block_hashes_in_range(
            self, start_from_height: int, limit: int, serialize: bool
    ) -> typing.List[typing.Optional[bytes]]:
        def fn(_h):
            res = self._get_block_hash(int.to_bytes(_h, 4, 'little'))
            if res and serialize:
                return res
            return res

        return list(map(fn, range(start_from_height, start_from_height + 1 + limit)))

    async def save_blocks(self, blocks: typing.Iterable[Block]) -> typing.List[Block]:
        try:
            await self._save_blocks_lock.acquire()
            start = time.time()
            res = await self.loop.run_in_executor(
                self.executor,
                self._save_blocks,
                blocks
            )
            Logger.repository.debug('Saved %s blocks in %s', len(res), time.time() - start)
            return res
        finally:
            self._save_blocks_lock.release()

    def _save_blocks(
            self,
            blocks: typing.List[Block]
    ) -> typing.List[Block]:
        current_local_chain_height = self.local_chain_height
        batch_session = self.leveldb.write_batch()
        response = []
        for i, block in enumerate(blocks):
            if block.height > self._best_header.height:
                raise exceptions.DatabaseInconsistencyException('Blocks > Headers')
            batch_session.put(
                self._get_db_key(DBPrefix.BLOCKS_INDEX, block.hash),
                len(block.data).to_bytes(4, 'little')
            )
            response.append(block)
            if block.height - 1:
                assert block.height == current_local_chain_height + 1
            if not block.height - 1 or (
                    current_local_chain_height != INT4_MAX and
                    current_local_chain_height == block.height - 1
            ):
                current_local_chain_height = block.height
            else:
                current_local_chain_height = INT4_MAX
        s = time.time()
        if current_local_chain_height != self.local_chain_height:
            batch_session.put(
                self._get_db_key(DBPrefix.LOCAL_CHAIN_HEIGHT),
                current_local_chain_height.to_bytes(4, 'little')
            )
            self._local_chain_height = current_local_chain_height
        batch_session.write()
        Logger.repository.debug('Blocks batch saved in %s', time.time() - s)
        return response

    async def get_block(self, block_hash: bytes) -> typing.Optional[Block]:
        response = (
            await self.loop.run_in_executor(
                self.executor,
                self._get_block,
                block_hash
            )
        )
        if not response:
            return
        block_data, height = response
        return Block(
            hash=block_hash,
            data=block_data,
            height=height
        )

    def _get_block(self, block_hash: bytes) -> (bytes, int):
        block_len = self.leveldb.get(self._get_db_key(DBPrefix.BLOCKS_INDEX, block_hash))
        if block_len is None:
            return
        block_len = block_len and int.from_bytes(block_len, 'little')
        block_data = self._disk_db.get_block(block_hash)
        if len(block_data) != block_len:
            raise exceptions.DatabaseInconsistencyException('inconsistency in blocks storage')
        block_header_and_height = self.leveldb.get(self._get_db_key(DBPrefix.HEADERS_INDEX, block_hash))
        if block_header_and_height is None:
            return
        assert len(block_header_and_height) == 84
        return block_data, int.from_bytes(block_header_and_height[80:], 'little')
