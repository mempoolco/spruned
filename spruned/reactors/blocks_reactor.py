import asyncio
import time
import typing
from concurrent.futures.process import ProcessPoolExecutor
from spruned.application.logging_factory import Logger
from spruned.reactors.headers_reactor import HeadersReactor
from spruned.services.p2p.block_deserializer import deserialize_block
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
        keep_block_absolute=None,
        max_blocks_per_round=8,
        block_fetch_timeout=15,
        deserialize_workers=2,
        max_blocks_buffer_megabytes=20,
        max_pending_requests=64
    ):

        assert keep_blocks_relative is None or keep_block_absolute is None  # one must be none

        self._repo = repository
        self._interface = interface
        self._loop = loop or asyncio.get_event_loop()
        self._headers = headers_reactor
        self._keep_blocks_relative = None
        self._keep_blocks_absolute = 650000
        self._max_blocks_per_round = max_blocks_per_round
        self._pending_blocks = dict()
        self._pending_blocks_no_answer = dict()
        self._pending_heights = set()
        self._blocks_sizes_by_hash = dict()
        self._block_fetch_timeout = block_fetch_timeout
        self._executor = ProcessPoolExecutor(max_workers=deserialize_workers)
        self._next_fetch_blocks_schedule = None
        self._started = False
        self._blocks_to_save = dict()
        self._local_current_block_height = None
        self._persisted_block_height = None
        self._lock = asyncio.Lock()
        self._blocks_queue = asyncio.Queue()
        self._size_items_in_queue = 0
        self._max_blocks_buffer_bytes = max_blocks_buffer_megabytes * 1024000
        self._processing_blocks_heights = set()
        self.initial_blocks_download = True
        self._max_pending_requests = max_pending_requests

    async def _save_blocks_to_disk(self):
        items = await self._blocks_queue.get()
        self._size_items_in_queue -= sum(map(lambda x: x['size'], items))
        await self._repo.blockchain.save_blocks(items)
        self._persisted_block_height = items[-1]['height']
        await asyncio.sleep(0.001)
        self._loop.create_task(self._save_blocks_to_disk())

    async def _deserialize_block(self, block: typing.Dict):
        block_bytes = block['header_bytes'] + block['data'].read()
        try:
            item = await self._loop.run_in_executor(
                self._executor,
                deserialize_block,
                block_bytes
            )
            if not item['success']:
                return
            return item['data']
        except (GeneratorExit, TypeError):
            Logger.p2p.warning('Error deserializing block')
            return

    def _remove_processing_height(self, height: int):
        try:
            self._processing_blocks_heights.remove(height)
        except KeyError:
            pass

    def _reschedule_fetch_blocks(self, reschedule_in: typing.Union[int, float]):
        assert self._next_fetch_blocks_schedule is None
        if reschedule_in == 0:
            self._loop.create_task(self._fetch_blocks_loop())
        else:
            self._next_fetch_blocks_schedule = self._loop.call_later(
                reschedule_in, lambda: self._loop.create_task(self._fetch_blocks_loop())
            )
        return

    @property
    def is_connected(self):
        return self._interface.is_connected()

    async def on_block(self, connection: P2PConnection, block: typing.Dict):
        if block['block_hash'] in self._pending_blocks or self._pending_blocks_no_answer:
            connection.add_success()
            await self._on_block_received(block, connection)

    async def _on_block_received(self, block: typing.Dict, connection: P2PConnection):
        pending_task = self._pending_blocks_no_answer.pop(
            block['block_hash'],
            self._pending_blocks.pop(block['block_hash'], None)
        )
        if not pending_task:
            return
        height = pending_task[1]  # height - we really have to fix built-in types.
        block['block_height'] = height
        if height in self._processing_blocks_heights:
            return

        self._processing_blocks_heights.add(height)
        height in self._pending_heights and self._pending_heights.remove(height)
        if height <= self._local_current_block_height:
            return
        deserialized_block = await self._deserialize_block(block)
        if not deserialized_block:
            connection.add_error()
            self._processing_blocks_heights.remove(height)
            return

        deserialized_block['height'] = height
        self._blocks_to_save[height] = deserialized_block
        self._blocks_sizes_by_hash[block['block_hash']] = deserialized_block['size']
        self._processing_blocks_heights.remove(height)
        connection.add_success()

    async def _save_blocks(self):
        """
        wait to stack contiguous blocks to the current height, before saving
        """
        if not self._blocks_to_save:
            return
        contiguous = []
        for _h in sorted(list(self._blocks_to_save)):
            if _h <= self._local_current_block_height:
                block = self._blocks_to_save.pop(_h)
                self._blocks_sizes_by_hash.pop(block['hash'])
            elif not contiguous and _h == self._local_current_block_height + 1:
                contiguous.append(_h)
            elif contiguous and _h == contiguous[-1] + 1:
                contiguous.append(_h)
            else:
                break
        if not contiguous:
            return
        blocks_to_save = []
        for block_height in contiguous:
            block = self._blocks_to_save.pop(block_height)
            blocks_to_save.append(block)
            self._blocks_sizes_by_hash.pop(block['hash'])
        await self._blocks_queue.put(blocks_to_save)
        self._size_items_in_queue += sum(map(lambda x: x['size'], blocks_to_save))
        current_height = contiguous[-1]
        Logger.p2p.debug('Saved blocks. Set local current block height: %s', current_height)
        self._local_current_block_height = current_height

    async def start(self, *a, **kw):
        assert not self._started
        self._started = True
        if self._keep_blocks_relative is None and self._keep_blocks_absolute is None:
            Logger.p2p.debug('No fetching rules for the BlocksReactor')
            return
        self._loop.create_task(self._save_blocks_to_disk())
        await self._fetch_blocks_loop()

    async def _check_pending_blocks(self):
        now = time.time()
        for blockhash, fetch_time_and_blockheight in list(self._pending_blocks.items()):
            fetch_time, blockheight = fetch_time_and_blockheight
            if now - fetch_time > self._block_fetch_timeout:
                self._pending_blocks_no_answer[blockhash] = self._pending_blocks.pop(blockhash)
                self._pending_heights.remove(self._pending_blocks_no_answer[blockhash][1])

    async def _fetch_blocks_loop(self):
        self._next_fetch_blocks_schedule = None
        await self._lock.acquire()
        try:
            await self._save_blocks()
            await self._fetch_blocks()
        finally:
            not self._next_fetch_blocks_schedule and self._reschedule_fetch_blocks(60)
            self._lock.release()

    async def _fetch_blocks(self):
        if not self.is_connected:
            return self._reschedule_fetch_blocks(1)
        if self._headers.initial_headers_download:
            return self._reschedule_fetch_blocks(1)
        self._pending_blocks and await self._check_pending_blocks()
        head = await self._repo.blockchain.get_best_header()
        start_fetch_from_height = self._get_first_block_to_fetch(head['block_height'])
        if start_fetch_from_height is None:
            return self._reschedule_fetch_blocks(1)
        elif self._local_current_block_height is not None \
                and start_fetch_from_height < self._local_current_block_height:
            self.initial_blocks_download = False
            return self._reschedule_fetch_blocks(1)
        if self._local_current_block_height is None:
            self._persisted_block_height = self._local_current_block_height = start_fetch_from_height - 1
        await self._request_missing_blocks(start_fetch_from_height)
        return self._reschedule_fetch_blocks(0.1)

    def _get_first_block_to_fetch(self, head: int) -> typing.Optional[int]:
        if self._keep_blocks_relative is not None:
            return max(
                max(1, head - self._keep_blocks_relative + 1),  # enforce min block 1 (genesis block is hardcoded)
                self._local_current_block_height or 0
            )
        else:
            m = max(self._keep_blocks_absolute, self._local_current_block_height or 1)
            if head > m:
                return m

    async def _request_block(self, blockhash: bytes, blockheight: int):
        # fixme request multiple blocks.
        self._pending_blocks_no_answer.pop(blockhash, None)
        self._pending_blocks[blockhash] = [time.time(), blockheight]
        self._pending_heights.add(blockheight)
        await self._interface.request_block(blockhash)

    async def _request_missing_blocks(self, start_fetch_from_height: int):
        """
        continue to fetches and stack new blocks, filling holes made by failures.
        """
        round_slots = min(
            max(0, self._interface.get_free_slots() * 2 - len(self._pending_blocks)),
            max(0, self._max_blocks_per_round - len(self._pending_blocks))
        )
        if not round_slots:
            return
        fetching_blocks = []
        i = 0
        while round_slots > len(fetching_blocks):
            block_height = start_fetch_from_height + i
            blocks_buffer_size = sum(self._blocks_sizes_by_hash.values() or (0, ))
            total_buffer_size = self._size_items_in_queue + blocks_buffer_size
            if total_buffer_size > self._max_blocks_buffer_bytes:
                max_pending_height = self._blocks_to_save and \
                                     max(map(lambda b: b['height'], self._blocks_to_save.values()))
                if not max_pending_height or block_height > max_pending_height:
                    await asyncio.sleep(2)
                    Logger.p2p.debug(
                        'Buffer size near max value (%s - %s), sleeping',
                        blocks_buffer_size, self._size_items_in_queue
                    )
                    break
                pending_requests = len(self._pending_blocks) + len(self._pending_blocks_no_answer) * .5
                if pending_requests > self._max_pending_requests and \
                        not max_pending_height or block_height > max_pending_height:
                    await asyncio.sleep(2)
                    Logger.p2p.debug(
                        'Max pending requests: %s, sleeping',
                        pending_requests
                    )
                    break
            if block_height in self._processing_blocks_heights or \
                    block_height in self._blocks_to_save or \
                    block_height in self._pending_heights:
                i += 1
                continue
            fetching_blocks.append(block_height)
            i += 1
        block_hashes = await asyncio.gather(
            *map(
                self._repo.blockchain.get_block_hash,
                fetching_blocks
            )
        )
        for i, height_and_hash in enumerate(zip(fetching_blocks, block_hashes)):
            height, blockhash = height_and_hash
            if not blockhash:
                break
            blockhash_bytes = bytes.fromhex(blockhash)
            await self._request_block(blockhash_bytes, height)
