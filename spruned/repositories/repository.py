import asyncio
import time

import typing
from aiodiskdb import AioDiskDB

from spruned.application import ioc
from spruned.application.tools import blockheader_to_blockhash
from spruned.repositories.chain_repository import BlockchainRepository


class Repository:
    def __init__(self, blockchain_repository):
        self._blockchain_repository = blockchain_repository
        self.diskdb: typing.Optional[AioDiskDB] = None
        self.leveldb = None

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
            asyncio.get_event_loop().create_task(self.diskdb.run())
            s = time.time()
            if not self.diskdb.running:
                await asyncio.sleep(0.1)
                if time.time() - s > 2:
                    raise ValueError('DB Init Error')
            await self.blockchain.initialize(block)
            await self.diskdb.stop()
        asyncio.get_event_loop().run_until_complete(_init())
