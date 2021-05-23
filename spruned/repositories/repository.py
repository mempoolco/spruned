import asyncio

from spruned import settings
from spruned.application import database
from spruned.repositories.blockchain_repository import BlockchainRepository
from spruned.repositories.mempool_repository import MempoolRepository


class Repository:
    def __init__(self, blocks, mempool, keep_blocks=6):
        self._blockchain_repository = blocks
        self._mempool_repository = mempool
        self.session = None
        self.cache = None
        self.keep_blocks = keep_blocks
        self.integrity_lock = asyncio.Lock()

    @property
    def blockchain(self) -> BlockchainRepository:
        return self._blockchain_repository

    @property
    def mempool(self) -> (MempoolRepository, None):
        return self._mempool_repository

    @classmethod
    def instance(cls):  # pragma: no cover
        from spruned.application.context import ctx
        blocks_repository = BlockchainRepository(
            database.level_db,
            settings.LEVELDB_PATH
        )
        mempool_repository = ctx.mempool_size and MempoolRepository(
            max_size_bytes=ctx.mempool_size*1024000
        ) or None

        i = cls(
            blocks=blocks_repository,
            mempool=mempool_repository,
            keep_blocks=ctx.keep_blocks
        )
        i.session = database.level_db
        return i

    def set_cache(self, cache):
        self.cache = cache
        self.blockchain.set_cache(cache)
