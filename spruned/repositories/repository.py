from spruned import settings
from spruned.repositories.headers_repository import HeadersSQLiteRepository
from spruned.repositories.blockchain_repository import BlockchainRepository


class Repository:
    def __init__(self, headers, blocks):
        self._headers_repository = headers
        self._blockchain_repository = blocks

    @property
    def headers(self) -> HeadersSQLiteRepository:
        return self._headers_repository

    @property
    def blockchain(self) -> BlockchainRepository:
        return self._blockchain_repository

    @classmethod
    def instance(cls):
        from spruned.application import database
        headers_repository = HeadersSQLiteRepository(database.sqlite)
        blocks_repository = BlockchainRepository(
            database.storage_ldb,
            settings.LEVELDB_BLOCKCHAIN_SLUG,
            settings.LEVELDB_BLOCKCHAIN_ADDRESS
        )
        return cls(
            headers=headers_repository,
            blocks=blocks_repository
        )

    def ensure_integrity(self):
        #self.headers.ensure_integrity()
        #self.blockchain.ensure_integrity()
        pass

    def set_cache(self, cache):
        self.headers.set_cache(cache)
        self.blockchain.set_cache(cache)
