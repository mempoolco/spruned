import asyncio
from spruned.application import database
from spruned.repositories.chain_repository import BlockchainRepository


class Repository:
    def __init__(self, blockchain_repository):
        self._blockchain_repository = blockchain_repository
        self.integrity_lock = asyncio.Lock()

    @property
    def blockchain(self) -> BlockchainRepository:
        return self._blockchain_repository

    @classmethod
    def instance(cls):  # pragma: no cover
        diskdb = database.disk_db
        blockchain_repository = BlockchainRepository(
            diskdb, database.level_db
        )

        i = cls(blockchain_repository)
        return i

    async def initialize(self):
        await self.integrity_lock.acquire()
        try:
            from spruned.application.context import ctx
            await self.blockchain.initialize(
                ctx.network_rules['genesis_block']
            )
        finally:
            self.integrity_lock.release()
