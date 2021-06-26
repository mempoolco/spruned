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
from spruned.application.process_pool_manager import ProcessPoolManager

_EMPTY_MEM = [b'\x00' * 36 for _ in range(254)]

import asyncio
import multiprocessing
from concurrent.futures.process import ProcessPoolExecutor
from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum

import typing
from multiprocessing.shared_memory import ShareableList

import lmdb

from spruned.application.logging_factory import Logger
from spruned.repositories.utxo_blocks_processor import BlockProcessor
from spruned.repositories.utxo_diskdb import UTXODiskDB


class DBPrefix(Enum):
    DB_VERSION = b'\x00\x01'
    CURRENT_BLOCK_HEIGHT = b'\x00\x02'
    UTXO = b'\x00\x03'
    UTXO_REVERTS = b'\x00\x04'
    UTXO_BY_SHARD = b'\x00\x05'


class UTXOXOFullRepository:
    def __init__(
        self,
        db: lmdb.Environment,
        db_path: str,
        disk_db: UTXODiskDB,
        multiprocessing_pool: ProcessPoolManager,
        multiprocessing_manager: multiprocessing.Manager,
        shards: typing.Optional[int] = 1000,
        parallelism=4,
        entries_to_fork=0
    ):
        self.db = db
        self.db_path = db_path
        self.loop = asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=16)
        self._best_header = None
        self._disk_db = disk_db
        self._safe_height = 0
        self._shards = shards
        self._manager = multiprocessing_manager
        self.parallelism = parallelism
        self.entries_to_fork = entries_to_fork
        self._multiprocessing = multiprocessing_pool

    def set_safe_height(self, safe_height: int):
        self._safe_height = safe_height

    @staticmethod
    def _get_db_key(prefix: DBPrefix, name: bytes = b''):
        return prefix.value + name

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
        if fork:
            requested_utxo = [ShareableList(_EMPTY_MEM)]
            published_utxo = self._manager.dict()
        else:
            requested_utxo, published_utxo = [list()], dict()
        responses = []
        Logger.utxo.info('Processing blocks, from %s to %s', blocks[0]['height'], blocks[-1]['height'])
        for chunk in self.get_chunks(blocks, self.parallelism):
            tasks = []
            if fork:
                lock = self._manager.Lock()
                processing_blocks = [ShareableList([None for _ in range(len(chunk))])]
                done_blocks = [ShareableList([None for _ in range(len(chunk))])]
                kill_pill = [ShareableList([None])]
            else:
                lock = None
                processing_blocks = [[None for _ in range(len(chunk))]]
                done_blocks = [[None for _ in range(len(chunk))]]
                kill_pill = [[None]]
            for i, b in enumerate(chunk):
                if kill_pill[0][0]:
                    break
                wip['pending'].append(b['height'])
                processing_blocks[0][i] = b['height']
                t = self.loop.run_in_executor(
                    self._multiprocessing.executor,
                    BlockProcessor.process,
                    b,
                    kill_pill if not fork else kill_pill[0].shm.name,
                    processing_blocks if not fork else processing_blocks[0].shm.name,
                    done_blocks if not fork else done_blocks[0].shm.name,
                    requested_utxo if not fork else requested_utxo[0].shm.name,
                    published_utxo,
                    min(self.parallelism if fork else 8, len(chunk)),
                    self._shards,
                    self.db_path,
                    responses,
                    not fork and self.db,
                    lock
                )
                tasks.append(t)
            res = await asyncio.gather(*tasks)
            if fork:
                processing_blocks[0].shm.unlink()
                done_blocks[0].shm.unlink()
                kill_pill[0].shm.unlink()
                del processing_blocks
                del done_blocks
                del kill_pill
            responses.extend(res)
            self.loop.create_task(self._populate_batch(res, write_batch, wip))
        if fork:
            assert all(map(lambda x: not x, requested_utxo[0])), requested_utxo
            requested_utxo[0].shm.unlink()
            del requested_utxo
        Logger.utxo.info('Processed blocks, from %s to %s', blocks[0]['height'], blocks[-1]['height'])

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
            for outpoint, value in r['new_utxo'].items():
                write_batch.put(DBPrefix.UTXO_BY_SHARD.value + value[1] + outpoint, b'\x01')
                write_batch.put(DBPrefix.UTXO.value + outpoint, value[0])
        for r in res:
            for outpoint, value in r['consumed_utxo'].items():
                write_batch.delete(DBPrefix.UTXO_BY_SHARD.value + value[1] + outpoint)
                write_batch.delete(DBPrefix.UTXO.value + outpoint)
            r['height'] in wip['pending'] and wip['pending'].remove(r['height'])
