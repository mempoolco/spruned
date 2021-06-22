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

import asyncio

import typing
from concurrent.futures.process import ProcessPoolExecutor

from spruned.application import ioc
from spruned.application.tools import blockheader_to_blockhash
from spruned.repositories.chain_repository import BlockchainRepository
from spruned.repositories.utxo_full_repository import UTXOXOFullRepository


class Repository:
    def __init__(self):
        self._utxo_repository: typing.Optional[UTXOXOFullRepository] = None
        self._blockchain_repository: typing.Optional[BlockchainRepository] = None
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
    def instance(cls, processes_pool: ProcessPoolExecutor):  # pragma: no cover
        blockchain_repository = BlockchainRepository(
            ioc.blockchain_db,
            ioc.blockchain_disk_db
        )
        utxo_repository = UTXOXOFullRepository(
            ioc.utxo_db,
            ioc.settings.UTXO_INDEX_PATH,
            ioc.utxo_disk_db,
            processes_pool,
            ioc.manager
        )
        i = cls()
        i.set_blockchain_repository(blockchain_repository)
        i.set_utxo_repository(utxo_repository)
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
