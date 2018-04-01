from unittest import TestCase
from unittest.mock import Mock, create_autospec

import pickle

import time

from spruned.application.cache import CacheAgent
from spruned.repositories.repository import Repository


class TestCacheAgent(TestCase):
    def setUp(self):
        self.session = Mock()
        self.repository = create_autospec(Repository)
        self.repository.ldb = self.session
        self.repository.blockchain.set_cache.return_value = None
        self.loopmock = Mock()
        self.delayer = Mock
        self.sut = CacheAgent(
            self.repository,
            1024,
            self.loopmock,
            self.delayer
        )
        self.basedata = {
            'keys': {
                'cafe': {
                    'saved_at': 123,
                    'size': 16,
                    'key': 'cafe'
                },
                'babe': {
                    'saved_at': 124,
                    'size': 32,
                    'key': 'babe'
                }
            },
            'total': 48
        }

    def test_init_no_data(self):
        self.session.get.return_value = None
        self.sut.init()

    def test_init_data(self):
        dump = pickle.dumps([['cafe', 123, 16], ['babe', 124, 32]])
        self.session.get.return_value = dump
        self.sut.init()
        self.assertEqual(self.sut._last_dump_size, 48)
        self.assertEqual(self.sut.index, self.basedata)
        self.assertEqual(self.sut.index['total'], 48)

    def test_save_data(self):
        dump = pickle.dumps([['cafe', 123, 16], ['babe', 124, 32]])
        self.session.get.return_value = dump
        self.sut.init()
        self.sut.dump()
        Mock.assert_called_once_with(self.session.put, b'cache_index', dump)

    def test_track(self):
        dump = pickle.dumps([['cafe', 123, 16], ['babe', 124, 32]])
        self.session.get.return_value = dump
        self.sut.init()
        now = int(time.time())
        self.sut.track('ffff', 64)
        self.assertEqual(self.sut.index['total'], 112)
        self.assertEqual(self.sut.index['keys']['ffff']['key'], 'ffff')
        self.assertEqual(self.sut.index['keys']['ffff']['size'], 64)
        self.assertTrue(now - 1 <= self.sut.index['keys']['ffff']['saved_at'] <= now + 1)

    def test_track_empty_index(self):
        now = int(time.time())
        self.sut.track('ffff', 64)
        self.assertEqual(self.sut.index['total'], 64)
        self.assertEqual(self.sut.index['keys']['ffff']['key'], 'ffff')
        self.assertEqual(self.sut.index['keys']['ffff']['size'], 64)
        self.assertTrue(now - 1 <= self.sut.index['keys']['ffff']['saved_at'] <= now + 1)
