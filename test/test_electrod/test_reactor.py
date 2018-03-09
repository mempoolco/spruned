import asyncio
import unittest
from unittest.mock import Mock, create_autospec
from spruned.application.abstracts import HeadersRepository
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon.electrod.electrod_reactor import ElectrodReactor
from spruned.daemon.electrod.electrod_rpc_server import ElectrodRPCServer
from test.utils import async_coro, call_name
import warnings


class TestElectrodReactor(unittest.TestCase):
    def setUp(self):
        self.repo = create_autospec(HeadersRepository)
        self.interface = create_autospec(ElectrodInterface)
        self.rpc_server = create_autospec(ElectrodRPCServer)
        self.electrod_loop = Mock()
        self.sut = ElectrodReactor(self.repo, self.interface, self.rpc_server, loop=self.electrod_loop)
        self.loop = asyncio.get_event_loop()
        warnings.filterwarnings("ignore")

    def tearDown(self):
        self.repo.reset_mock()
        self.interface.reset_mock()
        self.rpc_server.reset_mock()
        self.electrod_loop.reset_mock()

    def test_no_local_best_header(self):
        """
        bootstrapping test
        """
        self.interface.get_last_network_best_header.return_value = async_coro(None)
        self.loop.run_until_complete(self.sut.sync_headers())
        Mock.assert_called_once_with(self.electrod_loop.call_later, 30, call_name('sync_headers'))
        Mock.assert_not_called(self.interface)
        self.assertEqual(1, len(self.interface.method_calls))
        self.assertEqual(1, len(self.electrod_loop.method_calls))
        self.assertEqual(0, len(self.repo.method_calls))
        self.assertEqual(0, len(self.rpc_server.method_calls))

    def test_network_header_behind(self):
        """
        network header behind
        """
        peer = Mock()
        net_header = {'block_height': 1, 'block_hash': 'ff'*32}
        loc_header = {'block_height': 2, 'block_hash': 'ff'*32}
        self.interface.get_last_network_best_header.return_value = async_coro((peer, net_header))
        self.interface.disconnect_from_peer.return_value = async_coro(True)
        self.repo.get_best_header.return_value = loc_header
        self.repo.get_header_at_height.return_value = loc_header
        self.loop.run_until_complete(self.sut.sync_headers())
        Mock.assert_called_with(peer.close)
        Mock.assert_called_with(self.repo.get_header_at_height, 2)
        Mock.assert_called_once_with(self.electrod_loop.call_later, 0, call_name('sync_headers'))
        self.assertEqual(2, len(self.interface.method_calls))
        self.assertEqual(1, len(self.electrod_loop.method_calls))
        self.assertEqual(2, len(self.repo.method_calls))
        self.assertEqual(0, len(self.rpc_server.method_calls))
