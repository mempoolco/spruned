import asyncio

from spruned import settings
from spruned.application.database import ldb_batch
from spruned.application.logging_factory import Logger
from spruned.repositories.headers_repository import HeadersSQLiteRepository
from spruned.repositories.blockchain_repository import BlockchainRepository, TRANSACTION_PREFIX, BLOCK_INDEX_PREFIX, \
    DB_VERSION
from spruned.repositories.mempool_repository import MempoolRepository


class Repository:
    def __init__(self, headers, blocks, mempool, keep_blocks=200):
        self._headers_repository = headers
        self._blockchain_repository = blocks
        self._mempool_repository = mempool
        self.ldb = None
        self.sqlite = None
        self.cache = None
        self.keep_blocks = keep_blocks
        self.integrity_lock = asyncio.Lock()

    @property
    def headers(self) -> HeadersSQLiteRepository:
        return self._headers_repository

    @property
    def blockchain(self) -> BlockchainRepository:
        return self._blockchain_repository

    @property
    def mempool(self) -> (MempoolRepository, None):
        return self._mempool_repository

    @classmethod
    def instance(cls):  # pragma: no cover
        from spruned.application import database
        from spruned.application.context import ctx
        headers_repository = HeadersSQLiteRepository(database.sqlite)
        blocks_repository = BlockchainRepository(
            database.storage_ldb,
            settings.LEVELDB_BLOCKCHAIN_SLUG,
            settings.LEVELDB_BLOCKCHAIN_ADDRESS
        )
        if ctx.mempool_size > 1000:
            Logger.mempool.error(
                'Initializing mempool, are you sure you need a %s megabytes mempool?',
                ctx.mempool_size*1024000
            )
            raise ValueError('Max mempool size: 1000mb')
        mempool_repository = ctx.mempool_size and MempoolRepository(max_size_bytes=ctx.mempool_size*1024000) or None

        i = cls(
            headers=headers_repository,
            blocks=blocks_repository,
            mempool=mempool_repository,
            keep_blocks=ctx.keep_blocks
        )
        i.sqlite = database.sqlite
        i.ldb = database.storage_ldb
        return i

    async def ensure_integrity(self):
        try:
            await self.integrity_lock.acquire()
            self._ensure_no_stales_in_blockchain_repository()
        finally:
            self.integrity_lock.release()

    @ldb_batch
    def _ensure_no_stales_in_blockchain_repository(self):
        Logger.leveldb.debug('Ensuring no stales in blockchain repository')
        keypref = self.blockchain.storage_name + b'.' + BLOCK_INDEX_PREFIX
        extemp = self.get_extemped_blockhash()
        keep_keys = [self.blockchain.get_key(e, keypref) for e in extemp]
        index = self.cache.get_index()
        if not index:
            Logger.cache.debug('Cache index not found')
            return
        index = [self.blockchain.storage_name + b'.' + k for k in index.get('keys', {}).keys()]
        if not index:
            Logger.cache.debug('Empty index found')
        iterator = self.ldb.iterator(prefix=keypref, include_value=False)
        purged = 0
        txs = 0
        cached = 0
        tot = -2  # skip cache index & db_version
        kept = 0
        for x in iterator:
            tot += 1
            if keypref not in x:
                if x in (
                        self.cache.cache_name,
                        self.blockchain.storage_name + b'.' + DB_VERSION
                ):
                    continue
                elif self.blockchain.storage_name + b'.' + TRANSACTION_PREFIX in x:
                    txs += 1
                    continue
            if x in keep_keys:
                kept += 1
                continue
            elif x in index:
                cached += 1
                continue
            elif x not in index:
                Logger.repository.debug('Purging block %s' % x)
                self.blockchain.remove_block(x.replace(keypref + b'.', b''))
                purged += 1
            else:
                raise ValueError(x)
        Logger.cache.info(
            '\nPurged from storage %s elements not tracked by cache.\n'
            'Total tracked: %s\n'
            'Total protected: %s,\n'
            'Total cached: %s,\n'
            'Total entries: %s,\n'
            'Total transactions: %s\n',
            purged, len(index), kept, cached, tot, txs
        )
        return

    def set_cache(self, cache):
        self.cache = cache
        self.headers.set_cache(cache)
        self.blockchain.set_cache(cache)

    def get_extemped_blockhash(self):
        """
        avoid to delete headers in range
        """
        best_header = self.headers.get_best_header()
        _keep_to = best_header and best_header.get('block_height') or 0
        keep_from = _keep_to - self.keep_blocks if _keep_to - self.keep_blocks > 0 else 0
        keep_headers = keep_from and self.headers.get_headers_since_height(keep_from) or []
        keep_hashes = [k.get('block_hash') for k in keep_headers]
        return keep_hashes
