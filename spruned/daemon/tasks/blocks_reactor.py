import asyncio
import typing

from spruned.application.logging_factory import Logger
from spruned.daemon.p2p.p2p_interface import P2PInterface
from spruned.repositories.repository import Repository


class BlocksReactor:
    def __init__(
            self,
            repository: Repository,
            interface: P2PInterface,
            loop=asyncio.get_event_loop(),
            keep_blocks=6,
    ):
        self.repo = repository
        self.interface = interface
        self.loop = loop or asyncio.get_event_loop()
        self.lock = asyncio.Lock()
        self._last_processed_block = None
        self._keep_blocks = keep_blocks
        self._available = False
        self._fetching_blocks = set()
        self._missing_blocks = set()
        self._healthy = True

    def set_last_processed_block(self, last: typing.Optional[typing.Dict]):
        if last and last != self._last_processed_block:
            self._last_processed_block = last
            Logger.p2p.info(
                'Last processed block: %s (%s)',
                self._last_processed_block and self._last_processed_block['block_height'],
                self._last_processed_block and self._last_processed_block['block_hash']
            )

    @staticmethod
    def on_header(best_header: typing.Dict):
        Logger.p2p.debug('BlocksReactor.on_header: %s', best_header)

    async def on_connected(self):
        self._available = True

    async def start(self, *a, **kw):
        self.interface.add_on_connect_callback(self.on_connected)
        self.loop.create_task(self.interface.start())
        await self._fetch_blocks_loop()
        self._healthy = False

    async def _save_block(self, blockhash: str):
        try:
            block = await self.interface.get_block(blockhash, timeout=30)
            await self.repo.blockchain.save_block(block)
        except:
            self._missing_blocks.add(blockhash)
            Logger.p2p.debug('Error fetching block', exc_info=True)
        finally:
            self._fetching_blocks.remove(blockhash)

    async def check_missing_blocks(self):
        if not self._available:
            return

        free_slots = self.interface.get_free_slots()
        if not free_slots:
            return

        best_header = self.repo.headers.get_best_header()
        headers = self.repo.headers.get_headers_since_height(
            best_header['block_height'] - self._keep_blocks,
            limit=free_slots
        )
        for blockheader in headers:
            blockhash = blockheader['block_hash']
            if blockhash not in self._fetching_blocks and \
                    blockhash not in self._missing_blocks and \
                    not await self.repo.blockchain.get_block_index(blockhash):
                self._missing_blocks.add(blockhash)

    async def _fetch_blocks_loop(self):
        while 1:
            await self.check_missing_blocks()
            if self._missing_blocks:
                await self._get_blocks()
            await asyncio.sleep(0.01)

    async def _get_blocks(self):
        round_size = min(len(self._missing_blocks), self.interface.get_free_slots())
        _temp = set({self._missing_blocks.pop() for _ in range(round_size)})
        self._fetching_blocks.update(_temp)
        for block in _temp:
            self.loop.create_task(self._save_block(block))
