import asyncio
import pickle
from leveldb import LevelDB
import time
from spruned.application.database import storage_ldb
from spruned.application.logging_factory import Logger
from spruned.application.tools import async_delayed_task
from spruned.repositories.blockchain_repository import TRANSACTION_PREFIX, BLOCK_PREFIX


class CacheAgent:
    def __init__(self, repository, limit, loop=asyncio.get_event_loop(), delayer=async_delayed_task):
        self.session: LevelDB = repository.session
        self.repository = repository
        self.repository.set_cache(self)
        self.cache_name = b'cache_index'
        self.index = {}
        self.limit = limit
        self._last_dump_size = None
        self.loop = loop
        self.lock = asyncio.Lock()
        self.delayer = delayer

    def init(self):
        self._load_index()

    def dump(self):
        self._save_index()

    def _deserialize_index(self, rawdata):
        index = {}
        data = pickle.loads(rawdata)
        s = 0
        for d in data:
            s += d[5]
            index[d[0]] = {
                'saved_at': d[1],
                'ref': d[2],
                'size': d[3],
                'key': d[0]
            }
        index['total_size'] = s
        self._index = index
        return index

    def _serialize_index(self):
        data = []
        for k, d in self.index.items():
            data.append([k, d['saved_at'], d['ref'], d['size']])
        return pickle.dumps(data)

    @storage_ldb
    def _save_index(self):
        data = self._serialize_index()
        self.session.Put(data)
        self._last_dump_size = self.index['total']

    def _load_index(self):
        index = self.session.Get(self.cache_name)
        self._deserialize_index(index)
        self._last_dump_size = self.index['total']

    def track(self, key, ref, size):
        self.index[key] = {
            'saved_at': int(time.time()),
            'ref': ref,
            'size': size
        }
        self.index['total'] += size

    @storage_ldb
    def check(self):
        if not self.index:
            Logger.cache.debug('No prev index found, trying to load')
            self._load_index()
        if not self.index:
            Logger.cache.debug('No prev index found nor loaded')
            return
        if self.index['total'] > self.limit:
            Logger.cache.debug('Purging cache, size: %s, limit: %s', self.index['total'], self.limit)
            blockfirst = {BLOCK_PREFIX: 2, TRANSACTION_PREFIX: 1}
            index_sorted = sorted(self.index.values(), key=lambda x: x[blockfirst[x['ref'][0]]]**33 - x['saved_at'])
            i = 0
            while self.index['total'] * 1.1 > self.limit:
                self.delete(index_sorted[i])
                i += 1
        else:
            Logger.cache.debug('Cache is ok, size: %s, limit: %s', self.index['total'], self.limit)
        if self.index['total'] != self._last_dump_size:
            self._save_index()

    @storage_ldb
    def delete(self, key, entry):
        if entry['ref'][0] == BLOCK_PREFIX:
            self.repository.delete_block(entry['ref'])
        elif entry['ref'][0] == TRANSACTION_PREFIX:
            self.repository.delete_transaction(entry['ref'])
        self.index['total'] -= self.index.pop(key)['size']

    async def lurk(self):
        try:
            await self.lock.acquire()
            await self.loop.run_in_executor(None, self.check)
        finally:
            self.lock.release()
            self.loop.create_task(self.delayer(self.lurk, 30))
