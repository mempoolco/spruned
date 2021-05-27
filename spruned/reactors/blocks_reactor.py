import asyncio
import time
import typing
from concurrent.futures.process import ProcessPoolExecutor

from spruned.application.logging_factory import Logger
from spruned.reactors.headers_reactor import HeadersReactor
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
            block_fetch_timeout=5,
            blocks_processors=2
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
        self._block_fetch_timeout = block_fetch_timeout
        self._blocks_processor = ProcessPoolExecutor(max_workers=blocks_processors)

    @property
    def is_connected(self):
        return self.interface.is_connected()

    async def on_block(self, block: typing.Dict):
        if block['block_hash'] not in self._pending_blocks:
            return
        pending_task = self._pending_blocks.pop(block['block_hash'])
        await self._on_block_received(pending_task, block)

    async def on_new_header(self, header: typing.Dict):
        # pass atm, rely on the loop
        pass

    async def start(self, *a, **kw):
        if self.keep_blocks_relative is None and self.keep_from_height is None:
            Logger.p2p.debug('No fetching rules for the BlocksReactor')
            return

        await self._fetch_blocks_loop()

    async def _check_pending_blocks(self):
        now = time.time()
        for blockhash, blockheight, fetch_time in self._pending_blocks.items():
            if now - fetch_time > self._block_fetch_timeout:
                await self._request_block(blockhash, blockheight)

    async def _fetch_blocks_loop(self):
        if self._pending_blocks:
            await self._check_pending_blocks()

        if not self.is_connected:
            # reschedule 5 seconds
            return
        if not self._headers.is_ready():
            # reschedule 30 seconds
            return
        head = await self.repo.blockchain.get_best_header()
        start_fetch_from_height = self._get_first_block_to_fetch(head['block_height'])
        if start_fetch_from_height is None:
            # reschedule 30 seconds
            return
        await self._request_for_missing_blocks(start_fetch_from_height)
        # reschedule 30 seconds

    def _get_first_block_to_fetch(self, head: int) -> typing.Optional[int]:
        if self.keep_blocks_relative is not None:
            return min(0, head - self.keep_blocks_relative)
        else:
            if head >= self.keep_from_height:
                return self.keep_from_height

    async def _request_block(self, blockhash: str, blockheight: int):
        self._pending_blocks[blockhash] = [time.time(), blockheight]
        await self.interface.request_block(blockhash)

    async def _request_for_missing_blocks(self, start_fetch_from_height: int):
        fetch_blocks = min(self.interface.get_free_slots(), self.max_blocks_per_round)
        for i, blockhash in enumerate(
            await self.repo.blockchain.get_block_hashes_in_range(
                start_from_height=start_fetch_from_height,
                limit=fetch_blocks
            )
        ):
            await self._request_block(blockhash, start_fetch_from_height + i)
        self.loop.create_task(self._fetch_blocks_loop())
