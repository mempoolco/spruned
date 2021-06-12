import asyncio

from spruned import settings
from spruned.application import database
from spruned.repositories.blockchain_repository import BlockchainRepository


class Repository:
    def __init__(self, blockchain_repository):
        self._blockchain_repository = blockchain_repository
        self.session = None
        self.cache = None
        self.integrity_lock = asyncio.Lock()

    @property
    def blockchain(self) -> BlockchainRepository:
        return self._blockchain_repository

    @classmethod
    def instance(cls):  # pragma: no cover
        from spruned.application.context import ctx
        blockchain_repository = BlockchainRepository(
            bytes.fromhex(ctx.network_rules['genesis_block']),
            database.level_db,
            settings.LEVELDB_PATH
        )

        i = cls(blockchain_repository)
        i.session = database.level_db
        return i

    def set_cache(self, cache):
        self.cache = cache
        self.blockchain.set_cache(cache)

    def initialize(self):
        self.blockchain.initialize()
