# The MIT License (MIT)
#
# Copyright (c) 2021 - spruned contributors - https://github.com/mempoolco/spruned
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import asyncio
import multiprocessing
from concurrent.futures.process import ProcessPoolExecutor
from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum

import typing
import lmdb

from spruned.application.logging_factory import Logger
from spruned.repositories.utxo_blocks_processor import BlockProcessor
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
        db: lmdb.Environment,
        db_path: str,
        disk_db: UTXODiskDB,
        processes_pool: ProcessPoolExecutor,
        multiprocessing_manager: multiprocessing.Manager,
        shards: typing.Optional[int] = 1000,
        parallelism=4,
        entries_to_fork=100
    ):
        self.db = db
        self.db_path = db_path
        self.loop = asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=16)
        self.multiprocessing = processes_pool
        self._best_header = None
        self._disk_db = disk_db
        self._safe_height = 0
        self._shards = shards
        self._manager = multiprocessing_manager
        self.parallelism = parallelism
        self.entries_to_fork = entries_to_fork

    def set_safe_height(self, safe_height: int):
        self._safe_height = safe_height

    @staticmethod
    def _get_db_key(prefix: DBPrefix, name: bytes = b''):
        assert isinstance(name, bytes)
        return b'%s%s' % (int.to_bytes(prefix.value, 2, "big"), name)

    @staticmethod
    def get_chunks(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    async def process_blocks(self, blocks: typing.List[typing.Dict]):
        """
        Process blocks using multiprocessing.
        Asynchronously prepare the WriteBatch.
        Save the batch using threading.
        """
        total_entries = sum(map(lambda x: x['total_entries'], blocks))
        avg_entries = total_entries / len(blocks)
        fork = avg_entries > self.entries_to_fork
        with self.db.begin(write=True) as batch:
            wip = dict(pending=[], errors=[], rev_states=[])
            await self._validate_blocks(blocks, batch, wip, fork=fork)
            while wip['pending']:
                if wip['errors']:
                    Logger.root.error('Found error in UTXO, not handled yet. Exiting: %s', wip['errors'])
                    self.loop.stop()
                await asyncio.sleep(0.001)
        Logger.utxo.info(
            'Processed %s UTXO%s. From block %s to %s (avg utxo per block: %s)',
            total_entries, ' (fork)' if fork else '', blocks[0]['height'], blocks[-1]['height'],
            int(avg_entries)
        )
        return True

    async def _validate_blocks(
            self, blocks: typing.List[typing.Dict],
            write_batch: lmdb.Transaction,
            wip: typing.Dict, fork: bool = False
    ):
        manager = self._manager
        responses = []
        for chunk in self.get_chunks(blocks, self.parallelism):
            tasks = []
            if fork:
                kill_pill, processing_blocks, done_blocks = manager.list(), manager.list(), manager.list()
                requested_utxo, published_utxo = manager.list(), manager.dict()
            else:
                kill_pill, processing_blocks, done_blocks = list(), list(), list()
                requested_utxo, published_utxo = list(), dict()
            for b in chunk:
                wip['pending'].append(b['height'])
                processing_blocks.append(b['height'])
                tasks.append(
                    self.loop.run_in_executor(
                        fork and self.multiprocessing or self.executor,
                        BlockProcessor.process,
                        b,
                        kill_pill,
                        processing_blocks,
                        done_blocks,
                        requested_utxo,
                        published_utxo,
                        min(self.parallelism if fork else 8, len(chunk)),
                        self._shards,
                        self.db_path,
                        responses,
                        not fork and self.db
                    )
                )
            res = await asyncio.gather(*tasks)
            responses.extend(res)
            self.loop.create_task(self._populate_batch(res, write_batch, wip))
        return responses

    async def _populate_batch(
            self,
            res: typing.Sequence[typing.Dict],
            write_batch: lmdb.Transaction,
            wip: typing.Dict
    ):
        for r in res:
            if r['exit_code'] not in (0, 991):
                Logger.utxo.error('Error! Response has exit code: %s', r)
                wip['errors'].append(
                    {
                        'height': r['height'],
                        'requested_utxo': r['requested_utxo'],
                        'exit_code': r['exit_code']
                    }
                )
                wip['pending'].remove(r['height'])
                continue
            if wip['errors']:
                wip['pending'].remove(r['height'])
                continue
            for outpoint, value in r['consumed_utxo'].items():
                write_batch.delete(self._get_db_key(DBPrefix.UTXO_BY_SHARD, value[1] + outpoint))
                write_batch.delete(self._get_db_key(DBPrefix.UTXO, outpoint))
            for outpoint, value in r['new_utxo'].items():
                write_batch.put(self._get_db_key(DBPrefix.UTXO_BY_SHARD, value[1] + outpoint), b'1')
                write_batch.put(self._get_db_key(DBPrefix.UTXO, outpoint), value[0])
            wip['pending'].remove(r['height'])
