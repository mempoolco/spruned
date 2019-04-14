import asyncio
import pickle
import time

from unittest import TestCase
from unittest.mock import Mock, create_autospec, call, ANY

from spruned.application.cache import CacheAgent
from spruned.repositories.repository import Repository


class TestCacheAgent(TestCase):
    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.session = Mock()
        self.repository = create_autospec(Repository)
        self.repository.ldb = self.session
        self.repository.blockchain.set_cache.return_value = None
        self.loopmock = Mock()
        self.delayer = Mock
        self.sut = CacheAgent(
            self.repository,
            1,
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

    def test_check_ok(self):
        dump = pickle.dumps([['cafe', 123, 16], ['babe', 124, 32]])
        self.session.get.return_value = dump
        self.sut.init()
        self.loop.run_until_complete(self.sut.check())
        Mock.assert_not_called(self.session.put)

    def test_check_new_data_saved(self):
        ldump = [['cafe', 123, 16], ['babe', 124, 32]]
        self.session.get.side_effect = [pickle.dumps(ldump), True, True, True]
        self.sut.init()
        self.sut.track('ffff', 64)
        ldump.append(['ffff', self.sut.index['keys']['ffff']['saved_at'], 64])
        self.loop.run_until_complete(self.sut.check())
        Mock.assert_called_once_with(self.session.put, b'cache_index', pickle.dumps(ldump))

    def test_check_new_data_saved_size_limit_exceeded(self):
        """
        this is the real naming convention for indexes
        :return:
        """
        ldump = [[b'\x02.cafe', 123, 512*1024], [b'\x02.babe', 124, 400*1024]]
        self.session.get.side_effect = [pickle.dumps(ldump), True, True, True, True]
        self.sut.init()
        self.sut.track(b'\x02.ffff', 640*1024)
        ldump.append([b'\x02.ffff', self.sut.index['keys'][b'\x02.ffff']['saved_at'], 640*1024])
        self.loop.run_until_complete(self.sut.check())
        Mock.assert_has_calls(
            self.session.put,
            calls=[
                call(b'cache_index', ANY),
                call(b'cache_index', ANY)
            ]
        )
        Mock.assert_has_calls(
            self.repository.blockchain.remove_block,
            calls=[call(b'cafe')]
        )
