import asyncio
from unittest import TestCase
from unittest.mock import Mock, create_autospec

from spruned.daemon.p2p import P2PInterface
from spruned.daemon.tasks.blocks_reactor import BlocksReactor
from spruned.repositories.repository import Repository
from test.utils import async_coro


class TestBlocksReactory(TestCase):
    def setUp(self):
        self.interface = create_autospec(P2PInterface)
        self.repo = create_autospec(Repository)
        self.loopmock = Mock()
        self.delayer = Mock()
        self.sut = BlocksReactor(self.repo, self.interface, self.loopmock, prune=5, delayed_task=self.delayer)
        self.loop = asyncio.get_event_loop()

    def test_check_blockchain_local_behind_remote(self):
        self.sut.set_last_processed_block({'block_hash': 'cafe', 'block_height': 9})
        self.repo.headers.get_best_header.return_value = {'block_hash': 'babe', 'block_height': 10}
        self.interface.get_blocks.return_value = async_coro({'babe': {'block_hash': 'babe', 'block_bytes': b'raw'}})
        self.repo.headers.get_headers_since_height.return_value = [{'block_hash': 'babe', 'block_height': 10}]
        self.repo.blockchain.get_block.return_value = None
        self.repo.blockchain.save_blocks.side_effect = lambda *x: x
        self.loop.run_until_complete(self.sut.check())
        Mock.assert_called_once_with(
            self.repo.blockchain.save_blocks, {'block_hash': 'babe', 'block_bytes': b'raw'}
        )
        self.assertEqual(self.sut._last_processed_block, {'block_hash': 'babe', 'block_height': 10})
        Mock.assert_called_once_with(self.repo.headers.get_best_header)
        Mock.assert_called_once_with(self.interface.get_blocks, 'babe')
        Mock.assert_called_once_with(self.repo.headers.get_headers_since_height, 9, limit=10)
        Mock.assert_called_once_with(self.repo.blockchain.get_block, 'babe', with_transactions=False)
        Mock.assert_called_once_with(self.repo.blockchain.save_blocks, {'block_hash': 'babe', 'block_bytes': b'raw'})
