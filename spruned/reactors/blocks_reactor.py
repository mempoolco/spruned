import asyncio
import time
import typing
from concurrent.futures.process import ProcessPoolExecutor
from spruned.application import exceptions
from spruned.application.logging_factory import Logger
from spruned.reactors.headers_reactor import HeadersReactor
from spruned.services.p2p.blocks_deserializer import deserialize_block
from spruned.services.p2p.connection import P2PConnection
from spruned.services.p2p.interface import P2PInterface
from spruned.repositories.repository import Repository


class BlocksReactor:
    def __init__(
        self,
        headers_reactor: HeadersReactor,
        repository: Repository,
        interface: P2PInterface,
        loop=asyncio.get_event_loop(),
        keep_blocks_relative=None,
        keep_block_from_height=None,
        max_blocks_per_round=4,
        block_fetch_timeout=10,
        deserialize_workers=4
    ):
        self.repo = repository
        self.interface = interface
        self.loop = loop or asyncio.get_event_loop()
        self._headers = headers_reactor
        self.keep_blocks_relative = keep_blocks_relative
        self.keep_from_height = keep_block_from_height
        assert keep_blocks_relative is None or keep_block_from_height is None  # one must be none
        self.max_blocks_per_round = max_blocks_per_round
        self._pending_blocks = dict()
        self._pending_blocks_no_answer = dict()
        self._block_fetch_timeout = block_fetch_timeout
        self.executor = ProcessPoolExecutor(max_workers=deserialize_workers)
        self.initial_blocks_download = True
        self._next_fetch_blocks_schedule = None
        self._started = False
        self._blocks_to_save = dict()
        self._local_current_block_height = 0
        self._fetch_lock = asyncio.Lock()
        self._save_lock = asyncio.Lock()

    async def _deserialize_block(self, block: typing.Dict):
        block_bytes = block['header_bytes'] + block['data'].read()
        item = await self.loop.run_in_executor(
            self.executor,
            deserialize_block,
            block_bytes
        )
        if not item['success']:
            raise exceptions.DeserializeBlockException(item['error'])
        return item['data']

    def _reschedule_fetch_blocks(self, reschedule_in: int):
        assert self._next_fetch_blocks_schedule is None
        self._next_fetch_blocks_schedule = self.loop.call_later(
            reschedule_in, lambda: self.loop.create_task(self._fetch_blocks_loop())
        )
        return

    @property
    def is_connected(self):
        return self.interface.is_connected()

    async def on_block(self, connection: P2PConnection, block: typing.Dict):
        if block['block_hash'].hex() in self._pending_blocks or self._pending_blocks_no_answer:
            task = self._pending_blocks_no_answer.pop(block['block_hash'], None)
            task = task or self._pending_blocks.pop(block['block_hash'])
        else:
            # unwanted block
            return
        await self._on_block_received(task, block)

    async def _on_block_received(self, pending_task: typing.Dict, block: typing.Dict):
        deserialized_block = await self._deserialize_block(block)
        height = deserialized_block['block:height'] = pending_task[1]  # height - we really have to fix built-in types.
        self._blocks_to_save[height] = deserialized_block
        if height == self._local_current_block_height + 1:
            await self._save_blocks()

    async def _save_blocks(self):
        """
        wait to stack contiguous blocks to the current height, before saving
        """
        await self._save_lock.acquire()
        try:
            contiguous = []
            for i, h in enumerate(sorted(list(self._blocks_to_save))):
                if not i:
                    assert h['block_height'] == self._local_current_block_height + 1, h
                    contiguous.append(h['block_height'])
                else:
                    if h['block_height'] != contiguous[-1] + 1:
                        break
            await self.repo.blockchain.save_blocks(
                map(
                    lambda block_height: self._blocks_to_save.pop(block_height),
                    contiguous
                )
            )
            self._local_current_block_height = contiguous[-1]
        finally:
            self._save_lock.release()

    async def start(self, *a, **kw):
        assert not self._started
        self._started = True
        if self.keep_blocks_relative is None and self.keep_from_height is None:
            Logger.p2p.debug('No fetching rules for the BlocksReactor')
            return

        await self._fetch_blocks_loop()

    async def _check_pending_blocks(self):
        now = time.time()
        for blockhash, fetch_time_and_blockheight in list(self._pending_blocks.items()):
            fetch_time, blockheight = fetch_time_and_blockheight
            if now - fetch_time > self._block_fetch_timeout:
                self._pending_blocks_no_answer[blockhash] = self._pending_blocks.pop(blockhash)

    async def _fetch_blocks_loop(self):
        await self._fetch_lock.acquire()
        self._next_fetch_blocks_schedule = None
        try:
            if not self.is_connected:
                return self._reschedule_fetch_blocks(5)
            if self._headers.initial_headers_download:
                return self._reschedule_fetch_blocks(10)
            if self._pending_blocks:
                await self._check_pending_blocks()

            head = await self.repo.blockchain.get_best_header()
            start_fetch_from_height = self._get_first_block_to_fetch(head['block_height'])
            if start_fetch_from_height is None:
                return self._reschedule_fetch_blocks(30)
            await self._request_missing_blocks(start_fetch_from_height)
            self._reschedule_fetch_blocks(5)
        finally:
            self._fetch_lock.release()

    def _get_first_block_to_fetch(self, head: int) -> typing.Optional[int]:
        if self.keep_blocks_relative is not None:
            return min(0, head - self.keep_blocks_relative)
        else:
            if head >= self.keep_from_height:
                return self.keep_from_height

    async def _request_block(self, blockhash: str, blockheight: int):
        if self._pending_blocks_no_answer.get(blockhash):
            self._pending_blocks_no_answer.pop(blockhash)
        self._pending_blocks[bytes.fromhex(blockhash)] = [time.time(), blockheight]
        self.loop.create_task(self.interface.request_block(blockhash))

    async def _request_missing_blocks(self, start_fetch_from_height: int):
        fetch_blocks = min(
            max(0, self.interface.get_free_slots() - len(self._pending_blocks)),
            self.max_blocks_per_round
        )
        if not fetch_blocks:
            return
        hashes_in_range = await self.repo.blockchain.get_block_hashes_in_range(
            start_from_height=start_fetch_from_height,
            limit=fetch_blocks
        )
        for i, blockhash in enumerate(hashes_in_range):
            await self._request_block(blockhash, start_fetch_from_height + i)
