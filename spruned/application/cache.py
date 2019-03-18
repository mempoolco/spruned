import asyncio
import pickle
import time

from spruned.application.database import ldb_batch
from spruned.application.logging_factory import Logger
from spruned.application.tools import async_delayed_task
from spruned.repositories.blockchain_repository import BLOCK_PREFIX


class CacheAgent:
    def __init__(self, repository, limit, loop=asyncio.get_event_loop(), delayer=async_delayed_task):
        self.session = repository.ldb
        self.repository = repository
        self.repository.blockchain.set_cache(self)
        self.cache_name = b'cache_index'
        self.index = None
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
        index = {'keys': {}}
        data = pickle.loads(rawdata)
        s = 0
        for d in data:
            s += d[2]
            index['keys'][d[0]] = {
                'saved_at': d[1],
                'size': d[2],
                'key': d[0]
            }
        index['total'] = s
        self.index = index
        return index

    def _serialize_index(self):
        data = []
        sorted_data = sorted(self.index['keys'].values(), key=lambda x: x['saved_at'])
        for x in sorted_data:
            data.append([x['key'], x['saved_at'], x['size']])
        return pickle.dumps(data)

    @ldb_batch
    def _save_index(self):
        data = self._serialize_index()
        self.session.put(self.cache_name, data)
        Logger.cache.debug('Saved index')
        self._last_dump_size = self.index['total']

    def _load_index(self):
        index = self.session.get(self.cache_name)
        if not index:
            Logger.cache.warning('Cache not found. Ok if is the first time')
            return
        Logger.cache.debug('Loaded index')
        index and self._deserialize_index(index)
        self._last_dump_size = self.index and self.index['total']

    def track(self, key, size):
        if not self.index:
            self.index = {'keys': {}, 'total': 0}
        self.index['keys'][key] = {
            'saved_at': int(time.time()),
            'size': size,
            'key': key
        }
        self.index['total'] += size

    async def check(self):
        if self.index and self.index.get('keys') and not self._last_dump_size:
            Logger.cache.info('Pending data, dumping')
            self._save_index()
        if not self.index:
            Logger.cache.info('No prev index found, trying to load')
            self._load_index()
        if not self.index:
            self.index = {'keys': {}, 'total': 0}
            Logger.cache.info('No prev index found nor loaded')
            self._save_index()
            return
        else:
            self._purge_stales()
        if self.index['total'] > self.limit:
            Logger.cache.info('Purging cache, size: %s, limit: %s', self.index['total'], self.limit)
            blockfirst = {0: 2, 1: 1}
            index_sorted = sorted(
                self.index['keys'].values(), key=lambda x: ((blockfirst[x['key'][0]] ** 33) + x['saved_at'])
            )
            i = 0
            while self.index['total'] * 1.1 > self.limit:
                try:
                    if len(index_sorted) >= i:
                        item = index_sorted[i]
                        Logger.cache.debug('Deleting %s' % item)
                        self.delete(item)
                        i += 1
                    else:
                        break
                except IndexError:
                    break
        else:
            Logger.cache.info('Cache is ok, size: %s, limit: %s', self.index['total'], self.limit)
        if self.index['total'] != self._last_dump_size:
            self._save_index()

    def delete(self, item):
        if item['key'][0] == int.from_bytes(BLOCK_PREFIX, 'little'):
            Logger.leveldb.debug('Deleting block %s', item)
            self.repository.blockchain.remove_block(item['key'][2:])
        else:
            raise ValueError('Problem: %s' % item)
        self.index['total'] -= self.index['keys'].pop(item['key'])['size']

    async def lurk(self):
        try:
            await self.lock.acquire()
            await self.check()
        finally:
            self.lock.release()
            self.loop.create_task(self.delayer(self.lurk(), 600))

    def get_index(self):
        if not self.index:
            self._load_index()
        return self.index

    def _purge_stales(self):
        stales = []
        for key in self.index['keys']:
            if not self.session.get(self.repository.blockchain.storage_name + b'.' + key):
                stales.append(key)
        for stale in stales:
            self.index['total'] -= self.index['keys'].pop(stale)['size']
        Logger.cache.debug('Stales purge done, removed %s items from index', len(stales))
