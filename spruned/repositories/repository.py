import asyncio
import signal
import time

from spruned.application import ioc
from spruned.application.logging_factory import Logger
from spruned.application.tools import blockheader_to_blockhash
from spruned.repositories.chain_repository import BlockchainRepository


class Repository:
    def __init__(self, blockchain_repository):
        self._blockchain_repository = blockchain_repository
        self.leveldb = None
        self.loop = asyncio.get_event_loop()

    @property
    def blockchain(self) -> BlockchainRepository:
        return self._blockchain_repository

    @classmethod
    def instance(cls):  # pragma: no cover
        blockchain_repository = BlockchainRepository(ioc.blockchain_level_db)
        i = cls(blockchain_repository)
        i.leveldb = ioc.blockchain_level_db
        return i

    def initialize(self):
        from spruned.application.context import ctx
        genesis_block = bytes.fromhex(ctx.network_rules['genesis_block'])
        from spruned.repositories.repository_types import Block
        block = Block(
            blockheader_to_blockhash(genesis_block),
            genesis_block, height=0
        )
        asyncio.get_event_loop().run_until_complete(self.blockchain.initialize(block))
