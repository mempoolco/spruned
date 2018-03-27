from spruned import settings
from spruned.application.database import ldb_batch
from spruned.application.logging_factory import Logger
from spruned.repositories.headers_repository import HeadersSQLiteRepository
from spruned.repositories.blockchain_repository import BlockchainRepository


class Repository:
    def __init__(self, headers, blocks, keep_blocks=settings.BOOTSTRAP_BLOCKS):
        self._headers_repository = headers
        self._blockchain_repository = blocks
        self.ldb = None
        self.sqlite = None
        self.cache = None
        self.keep_blocks = keep_blocks

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
        i = cls(
            headers=headers_repository,
            blocks=blocks_repository
        )
        i.sqlite = database.sqlite
        i.ldb = database.storage_ldb
        return i

    def ensure_integrity(self):
        self._ensure_no_stales_in_blockchain_repository()

    @ldb_batch
    def _ensure_no_stales_in_blockchain_repository(self):
        extemp = self.get_extemped_blockhash()
        keep_keys = [self.blockchain.get_key(e, b'block') for e in extemp]
        index = self.cache.get_index()
        if not index:
            Logger.cache.debug('Cache index not found')
            return
        index = index.get('keys', {}).keys()
        if not index:
            Logger.cache.debug('Empty index found')
            return
        iterator = self.ldb.iterator()
        purged = 0
        for x in iterator:
            if x[0] not in index and x[0] != self.cache.cache_name and x[0] not in keep_keys:
                self.ldb.delete(x[0])
                purged += 1
        self.ldb.compact_range()
        Logger.cache.debug(
            'Purged from storage %s elements not tracked by cache, total tracked: %s',
            purged, len(index)
        )
        return

    def set_cache(self, cache):
        self.cache = cache
        self.headers.set_cache(cache)
        self.blockchain.set_cache(cache)

    def get_extemped_blockhash(self):
        best_header = self.headers.get_best_header()
        _keep_to = best_header and best_header.get('block_height')
        keep_from = _keep_to - 200 if _keep_to - 200 > 0 else 0
        keep_headers = keep_from and self.headers.get_headers_since_height(keep_from) or []
        keep_hashes = [k.get('block_hash') for k in keep_headers]
        return keep_hashes
