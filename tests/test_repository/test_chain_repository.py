from aiodiskdb import ItemLocation

from spruned import networks
from spruned.application.tools import blockheader_to_blockhash
from spruned.repositories.repository_types import Block
from . import RepositoryTestCase


class TestChainRepository(RepositoryTestCase):
    async def test(self):
        await self._run_diskdb()
        genesis_block = bytes.fromhex(networks.bitcoin.regtest['genesis_block'])
        initialize_response = await self.sut.initialize(
            Block(
                data=genesis_block,
                hash=blockheader_to_blockhash(genesis_block),
                height=0
            )
        )
        self.assertEqual(initialize_response.location, ItemLocation(0, 0, 285))
        self.assertEqual(initialize_response.data, genesis_block)
        self.assertEqual(initialize_response.height, 0)
        self.assertEqual(initialize_response.hash, blockheader_to_blockhash(genesis_block))
        get_block_response = await self.sut.get_block_hash(0)
        self.assertEqual(get_block_response, initialize_response.hash.hex())
        get_best_height_response = await self.sut.get_best_height()
        self.assertEqual(get_best_height_response, 0)
        await self.diskdb.stop()
