import asyncio

import typing

from spruned.application import ioc
from spruned.application.tools import blockheader_to_blockhash
from spruned.repositories.chain_repository import BlockchainRepository
from spruned.repositories.utxo_full_repository import UTXOXOFullRepository


class Repository:
    def __init__(self):
        self._utxo_repository: typing.Optional[UTXOXOFullRepository] = None
        self._blockchain_repository: typing.Optional[BlockchainRepository] = None
        self.leveldb = None
        self.diskdb = None
        self.loop = asyncio.get_event_loop()

    def set_blockchain_repository(self, repo: BlockchainRepository):
        self._blockchain_repository = repo
        return self

    def set_utxo_repository(self, repo: UTXOXOFullRepository):
        self._utxo_repository = repo
        return self

    @property
    def blockchain(self) -> BlockchainRepository:
        return self._blockchain_repository

    @property
    def utxo(self) -> UTXOXOFullRepository:
        return self._utxo_repository

    @classmethod
    def instance(cls):  # pragma: no cover
        blockchain_repository = BlockchainRepository(ioc.blockchain_level_db, ioc.blockchain_disk_db)
        utxo_repository = UTXOXOFullRepository(ioc.utxo_level_db, ioc.utxo_disk_db)
        i = cls()
        i.set_blockchain_repository(blockchain_repository)
        i.set_utxo_repository(utxo_repository)
        i.leveldb = ioc.blockchain_level_db
        i.diskdb = ioc.blockchain_disk_db
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
