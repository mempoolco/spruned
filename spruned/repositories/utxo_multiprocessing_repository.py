import asyncio
import multiprocessing
from concurrent.futures.process import ProcessPoolExecutor
from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum

import plyvel
import typing

from spruned.repositories.utxo_block_processor import BlockProcessor
from spruned.repositories.utxo_diskdb import UTXODiskDB


class DBPrefix(Enum):
    DB_VERSION = 1
    CURRENT_BLOCK_HEIGHT = 2
    UTXO = 3
    UTXO_REVERTS = 4
    UTXO_BY_SHARD = 5


class UTXOXOFullRepository:
    def __init__(
        self,
        db: plyvel.DB,
        db_path: str,
        disk_db: UTXODiskDB,
        shards: typing.Optional[int] = 1000,
    ):
        self.db = db
        self.db_path = db_path
        self.loop = asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=32)
        self.multiprocessing = ProcessPoolExecutor(max_workers=4)
        self._best_header = None
        self._disk_db = disk_db
        self._safe_height = 0
        self._shards = shards

    def set_safe_height(self, safe_height: int):
        self._safe_height = safe_height

    @staticmethod
    def _get_db_key(prefix: DBPrefix, name: bytes = b''):
        assert isinstance(name, bytes)
        return b'%s%s' % (int.to_bytes(prefix.value, 2, "big"), name)

    async def process_blocks(self, blocks: typing.List[typing.Dict]):
        tasks = []
        with multiprocessing.Manager() as manager:
            for b in blocks:
                tasks.append(
                    self.loop.run_in_executor(
                        self.multiprocessing, BlockProcessor.process, b, manager.list(),
                        manager.list(), manager.list(), manager.dict(), self.db_path
                    )
                )
            responses = await asyncio.gather(*tasks)
        return responses
