import asyncio
import signal
import time

import typing
from aiodiskdb import AioDiskDB

from spruned.application import ioc
from spruned.application.logging_factory import Logger
from spruned.application.tools import blockheader_to_blockhash
from spruned.repositories.chain_repository import BlockchainRepository


class Repository:
    def __init__(self, blockchain_repository):
        self._blockchain_repository = blockchain_repository
        self.diskdb: typing.Optional[AioDiskDB] = None
        self.leveldb = None
        self.loop = asyncio.get_event_loop()

    @property
    def blockchain(self) -> BlockchainRepository:
        return self._blockchain_repository

    @classmethod
    def instance(cls):  # pragma: no cover
        blockchain_repository = BlockchainRepository(
            ioc.disk_db, ioc.level_db
        )
        i = cls(blockchain_repository)
        i.diskdb = ioc.disk_db
        i.leveldb = ioc.level_db
        return i

    def initialize(self):
        from spruned.application.context import ctx
        genesis_block = bytes.fromhex(ctx.network_rules['genesis_block'])
        from spruned.repositories.repository_types import Block
        block = Block(
            blockheader_to_blockhash(genesis_block),
            genesis_block, height=0
        )

        async def _init():
            """
            Ensures the genesis block.
            """
            asyncio.get_event_loop().create_task(self.diskdb.run())
            await self._wait_for_diskdb()
            await self.blockchain.initialize(block)
            await self.diskdb.stop()

        asyncio.get_event_loop().run_until_complete(_init())
        self.diskdb.reset()  # bring the diskdb to the initial state

    async def _wait_for_diskdb(self):
        s = time.time()
        if not self.diskdb.running:
            await asyncio.sleep(0.1)
            if time.time() - s > 5:
                raise ValueError('DB Init Error')

    async def run(self):
        assert not self.diskdb.running
        signal.signal(signal.SIGINT, lambda *a: self.diskdb.on_stop_signal())
        signal.signal(signal.SIGTERM, lambda *a: self.diskdb.on_stop_signal())
        self.loop.create_task(self.diskdb.run())
        await self._wait_for_diskdb()
        Logger.repository.error('Repository started!')
