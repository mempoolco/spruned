import asyncio
import time
from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum

import typing
from functools import partial

import plyvel
from aiodiskdb import AioDiskDB, ItemLocation

from spruned.application import exceptions
from spruned.application.logging_factory import Logger
from spruned.application.tools import blockheader_to_blockhash
from spruned.repositories.repository_types import Block, BlockHeader


class DBPrefix(Enum):
    DB_VERSION = 1
    BLOCKS_INDEX = 2
    HEADERS_INDEX = 3
    BLOCKHASH_BY_HEIGHT = 4
    BEST_HEIGHT = 5


class BlockchainRepository:
    CURRENT_VERSION = 2

    def __init__(
        self,
        diskdb: AioDiskDB,
        leveldb: plyvel.DB
    ):
        self.diskdb = diskdb
        self.leveldb = leveldb
        self.loop = asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=64)
        self._best_header = None

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
        batch_session = self.leveldb.write_batch()
        genesis_block.location = await self.diskdb.add(genesis_block.data)
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
            self._get_db_key(DBPrefix.BLOCKS_INDEX, genesis_hash),
            genesis_block.location.serialize()
        )
        batch_session.put(
            self._get_db_key(DBPrefix.DB_VERSION),
            self.CURRENT_VERSION.to_bytes(2, 'little')
        )
        batch_session.write()
        await self.diskdb.flush()
        return genesis_block

    async def _ensure_genesis_block(self, genesis_block: Block):
        key = self._get_db_key(DBPrefix.BLOCKHASH_BY_HEIGHT, int(0).to_bytes(4, 'little'))
        current_genesis_hash = self.leveldb.get(key)
        expected_genesis_hash = blockheader_to_blockhash(genesis_block.data)
        if current_genesis_hash != expected_genesis_hash:
            raise exceptions.DatabaseInconsistencyException('invalid genesis hash stored')
        location = self.leveldb.get(
            self._get_db_key(DBPrefix.BLOCKS_INDEX, genesis_block.hash)
        )
        if not location:
            raise exceptions.DatabaseInconsistencyException('inconsistency db exception on diskdb')
        block_bytes = await self.diskdb.read(ItemLocation.deserialize(location))
        if not block_bytes or blockheader_to_blockhash(block_bytes) != genesis_block.hash:
            raise exceptions.DatabaseInconsistencyException('inconsistency db exception on hash')
        genesis_block.location = ItemLocation.deserialize(location)
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

    def get_headers(self, start_hash: bytes):
        return self.loop.run_in_executor(
            self.executor,
            self._get_headers,
            start_hash
        )

    def _get_headers(self, start_hash: bytes) -> typing.List[BlockHeader]:
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
        key = self._get_db_key(DBPrefix.BEST_HEIGHT)
        batch_session.put(key, height.to_bytes(4, 'little'))

        return height

    async def get_block_hash(self, height: int) -> bytes:
        resp = (
            await self.loop.run_in_executor(
                self.executor,
                self._get_block_hash,
                height.to_bytes(4, 'little')
            )
        )
        return resp

    def _get_block_hash(self, height: bytes):
        key = self._get_db_key(DBPrefix.BLOCKHASH_BY_HEIGHT, height)
        block_hash = self.leveldb.get(key)
        return block_hash and block_hash

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

    async def save_block(self, block: Block) -> Block:
        if block.height > self._best_header.height:
            raise exceptions.DatabaseInconsistencyException('cannot save a block > header')

        block.location = await self.diskdb.add(block.data)
        await self.loop.run_in_executor(
            self.executor,
            partial(self._save_block, block, self.leveldb)
        )
        await self.diskdb.flush()
        return block

    def _save_block(self, block: Block, batch_session: plyvel.DB) -> Block:
        batch_session.put(
            self._get_db_key(DBPrefix.BLOCKS_INDEX, block.hash),
            block.location.serialize()
        )
        return block

    async def save_blocks(self, blocks: typing.Iterable[Block]) -> typing.List[Block]:
        start = time.time()
        transaction = await self.diskdb.transaction()
        for block in blocks:
            transaction.add(block.data)
        locations = await transaction.commit()
        res = await self.loop.run_in_executor(
            self.executor,
            self._save_blocks,
            blocks, locations
        )
        Logger.repository.debug('Saved %s blocks in %s', len(res), time.time() - start)
        return res

    def _save_blocks(
            self,
            blocks: typing.Iterable[Block],
            locations: typing.List[ItemLocation]
    ) -> typing.List[Block]:
        batch_session = self.leveldb.write_batch()
        response = []
        for i, block in enumerate(blocks):
            batch_session.put(
                self._get_db_key(DBPrefix.BLOCKS_INDEX, block.hash),
                locations[i].serialize()
            )
            block.location = locations[i]
            response.append(self._save_block(block, batch_session))
        s = time.time()
        batch_session.write()
        Logger.repository.debug('Blocks batch saved in %s', time.time() - s)
        return response

    async def get_block(self, block_hash: bytes) -> typing.Optional[Block]:
        get_data_resp = (
            await self.loop.run_in_executor(
                self.executor,
                self._get_block_location,
                block_hash
            )
        )
        if not get_data_resp:
            return
        location, height = get_data_resp
        block_data = await self.diskdb.read(ItemLocation.deserialize(location))
        return Block(
            hash=block_hash,
            data=block_data,
            height=height,
            location=location
        )

    def _get_block_location(self, block_hash: bytes) -> (bytes, int):
        block_location = self.leveldb.get(self._get_db_key(DBPrefix.BLOCKS_INDEX, block_hash))
        if block_location is None:
            return
        block_heaader_and_height = self.leveldb.get(self._get_db_key(DBPrefix.HEADERS_INDEX, block_hash))
        if block_heaader_and_height is None:
            return
        assert len(block_heaader_and_height) == 84
        return block_location, int.from_bytes(block_heaader_and_height[80:], 'little')
