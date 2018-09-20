import asyncio
from unittest import TestCase
from unittest.mock import Mock

from spruned.repositories.blockchain_repository import BLOCK_PREFIX
from spruned.repositories.repository import Repository


class TestRepository(TestCase):
    def setUp(self):
        self.headers = Mock()
        self.blocks = Mock()
        self.mempool = Mock()
        self.cache = Mock(cache_name=b'cache_prefix')
        self.sut = Repository(self.headers, self.blocks, self.mempool, keep_blocks=5)
        self.sut.set_cache(self.cache)
        self.sut.ldb = Mock()
        self.loop = asyncio.get_event_loop()

    def tearDown(self):
        self.headers.reset_mock()
        self.blocks.reset_mock()
        self.cache.reset_mock()
        self.sut.ldb.reset_mock()

    def test_check_stales(self):
        self.headers.get_best_header.return_value = {'block_height': 16, 'block_hash': 'block10'}
        self.headers.get_headers_since_height.return_value = [
            {'block_height': 12, 'block_hash': 'block12'},
            {'block_height': 13, 'block_hash': 'block13'},
            {'block_height': 14, 'block_hash': 'block14'},
            {'block_height': 15, 'block_hash': 'block15'},
            {'block_height': 16, 'block_hash': 'block16'}
        ]
        self.blocks.storage_name = b'block_prefix'
        self.blocks.get_key.side_effect = lambda x, y: b'block_prefix.' + BLOCK_PREFIX + b'.' + x.encode()
        self.cache.get_index.return_value = {
            'keys': {
                b'block12': {},
                b'block13': {},
                b'block14': {},
                b'block15': {}
            }
        }
        iterator = [
            (b'block_prefix.block12',),
            (b'block_prefix.block13',),
            (b'block_prefix.block14',),
            (b'block_prefix.block15',),
            (b'block_prefix.block16',),
        ]
        self.sut.ldb.iterator.return_value = iterator
        self.loop.run_until_complete(self.sut.ensure_integrity())
        Mock.assert_called_once_with(self.blocks.remove_block, b'block_prefix.block16')

    def test_check_stales_no_index(self):
        self.headers.get_best_header.return_value = {'block_height': 16, 'block_hash': 'block10'}
        self.cache.get_index.return_value = None
        self.headers.get_headers_since_height.return_value = [
            {'block_height': 12, 'block_hash': 'block12'},
            {'block_height': 13, 'block_hash': 'block13'},
            {'block_height': 14, 'block_hash': 'block14'},
            {'block_height': 15, 'block_hash': 'block15'},
            {'block_height': 16, 'block_hash': 'block16'}
        ]
        self.blocks.storage_name = b'block_prefix'
        self.blocks.get_key.side_effect = lambda x, y: b'block_prefix.' + BLOCK_PREFIX + b'.' + x.encode()
        self.cache.get_index.return_value = None
        Mock.assert_not_called(self.blocks.remove_block)
