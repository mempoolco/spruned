import asyncio

from spruned import settings
from spruned.application import database
from spruned.repositories.blockchain_repository import BlockchainRepository
from spruned.repositories.mempool_repository import MempoolRepository


class Repository:
    def __init__(
            self,
            blockchain_repository,
            mempool_repository
    ):
        self._blockchain_repository = blockchain_repository
        self._mempool_repository = mempool_repository
        self.session = None
        self.cache = None
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
        blockchain_repository = BlockchainRepository(
            ctx.network_rules,
            database.level_db,
            settings.LEVELDB_PATH
        )
        mempool_repository = ctx.mempool_size and MempoolRepository(
            max_size_bytes=ctx.mempool_size * 1024000
        ) or None

        i = cls(
            blockchain_repository,
            mempool_repository
        )
        i.session = database.level_db
        return i

    def set_cache(self, cache):
        self.cache = cache
        self.blockchain.set_cache(cache)

    def initialize(self):
        self.blockchain.initialize()