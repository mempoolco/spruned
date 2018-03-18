import asyncio
import unittest
from unittest.mock import Mock, create_autospec

from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon.daemon_service import DaemonService
from test.utils import async_coro


class TestElectrodService(unittest.TestCase):
    def setUp(self):
        self.interface = create_autospec(ElectrodInterface)
        self.sut = DaemonService(self.interface)
        self.loop = asyncio.get_event_loop()
        self.assertEqual(self.sut.available, True)  # mmmh... this may be implemented

    def tearDown(self):
        self.interface.reset_mock()

    def test_getrawtransaction(self):
        self.interface.getrawtransaction.return_value = async_coro('ff'*32)
        res = self.loop.run_until_complete(self.sut.getrawtransaction('cafebabe'))
        self.assertEqual(res, 'ff'*32)
        Mock.assert_called_once_with(self.interface.getrawtransaction, 'cafebabe')

    def test_getrawtransaction_verbose(self):
        self.interface.getrawtransaction.return_value = async_coro('ff' * 32)
        res = self.loop.run_until_complete(self.sut.getrawtransaction('cafebabe', verbose=True))
        self.assertEqual(res, 'ff' * 32)
        Mock.assert_called_once_with(self.interface.getrawtransaction, 'cafebabe')

    def test_estimatefee(self):
        self.interface.estimatefee.return_value = async_coro(123)
        res = self.loop.run_until_complete(self.sut.estimatefee(6))
        self.assertEqual(res, 123)
        Mock.assert_called_once_with(self.interface.estimatefee, 6)

    def test_listunspents(self):
        self.interface.listunspents.return_value = async_coro({'unspents': 'list'})
        res = self.loop.run_until_complete(self.sut.listunspents('cafebabe'))
        self.assertEqual(res, {'unspents': 'list'})
        Mock.assert_called_once_with(self.interface.listunspents, 'cafebabe')

    def test_merkleproof(self):
        self.interface.get_merkleproof.return_value = async_coro({'merkle': 'proof'})
        res = self.loop.run_until_complete(self.sut.getmerkleproof('cafebabe', 10000))
        self.assertEqual(res, {'merkle': 'proof'})
        Mock.assert_called_once_with(self.interface.get_merkleproof, 'cafebabe', 10000)

