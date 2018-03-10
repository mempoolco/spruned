import asyncio
import unittest
from unittest.mock import Mock, create_autospec
from spruned.application.abstracts import HeadersRepository
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon.electrod.electrod_reactor import ElectrodReactor
from test.utils import async_coro, called_coroutine
import warnings


class TestElectrodReactor(unittest.TestCase):
    def setUp(self):
        self.repo = create_autospec(HeadersRepository)
        self.interface = create_autospec(ElectrodInterface)
        self.electrod_loop = Mock()
        self.sut = ElectrodReactor(self.repo, self.interface, loop=self.electrod_loop)
        self.loop = asyncio.get_event_loop()
        warnings.filterwarnings("ignore")

    def tearDown(self):
        self.repo.reset_mock()
        self.interface.reset_mock()
        self.electrod_loop.reset_mock()

    def test_no_network_best_header(self):
        """
        interface didn't returned any best header. will try again in 30 seconds
        """
        self.interface.get_last_network_best_header.return_value = async_coro(None)
        self.loop.run_until_complete(self.sut.check_headers())
        Mock.assert_called_once_with(self.electrod_loop.call_later, 30, called_coroutine('sync_headers'))
        Mock.assert_not_called(self.interface)
        self.assertEqual(1, len(self.interface.method_calls))
        self.assertEqual(1, len(self.electrod_loop.method_calls))
        self.assertEqual(0, len(self.repo.method_calls))

    def test_network_header_behind(self):
        """
        network header behind: remote peer outdated
        """
        peer = Mock()
        net_header = {'block_height': 1, 'block_hash': 'ff'*32}
        loc_header = {'block_height': 2, 'block_hash': 'ff'*32}
        self.interface.get_last_network_best_header.return_value = async_coro((peer, net_header))
        self.interface.disconnect_from_peer.return_value = async_coro(True)
        self.repo.get_best_header.return_value = loc_header
        self.repo.get_header_at_height.return_value = loc_header
        self.loop.run_until_complete(self.sut.check_headers())
        Mock.assert_called_with(peer.close)
        Mock.assert_called_with(self.repo.get_header_at_height, 2)
        Mock.assert_called_once_with(self.electrod_loop.call_later, 0, called_coroutine('sync_headers'))
        self.assertEqual(2, len(self.interface.method_calls))
        self.assertEqual(1, len(self.electrod_loop.method_calls))
        self.assertEqual(2, len(self.repo.method_calls))

    def test_network_equal(self):
        """
        electrod aligned with remote peers
        """
        peer = Mock()
        net_header = loc_header = {'block_height': 2, 'block_hash': 'ff' * 32}
        self.interface.get_last_network_best_header.return_value = async_coro((peer, net_header))
        self.repo.get_header_at_height(2).return_value = loc_header
        self.repo.get_best_header.return_value = loc_header
        self.repo.get_block_hash.return_value = 'ff' * 32
        self.loop.run_until_complete(self.sut.check_headers())
        Mock.assert_called_with(self.repo.get_header_at_height, 2)
        Mock.assert_called_once_with(self.electrod_loop.call_later, 120, called_coroutine('sync_headers'))
        self.assertEqual(1, len(self.interface.method_calls))
        self.assertEqual(1, len(self.electrod_loop.method_calls))
        self.assertEqual(3, len(self.repo.method_calls))

    def test_received_new_single_header(self):
        """
        header ff*32 is saved at height 2020
        received a new header at height 2021 with hash aa*32
        header is saved to disk
        best header is updated at height 2021
        """
        raise NotImplementedError

    def test_saved_orphan_header(self):
        """
        header ff*32 is saved at height 2020
        received a new header at height 2020 with hash 00*32
        oops. loop is paused for 20 seconds to allows the network to reorg.
        header at height 2020 is requested to the interface, quorum fails 3 times, then header 00*32 is returned
        reactor compare headers
        ff*32 is deleted by the repository
        00*32 is saved in the repository
        blockhash ff*32 is saved as orphan and will be ignored to avoid others peers to cause recursive inconsistencies
        """
        peer = Mock()
        net_header = loc_header = {'block_height': 2020, 'block_hash': 'ff' * 32}
        self.interface.get_last_network_best_header.return_value = async_coro((peer, net_header))
        self.repo.get_header_at_height(2).return_value = loc_header
        self.repo.get_best_header.return_value = loc_header
        self.repo.get_block_hash.return_value = '00' * 32
        self.loop.run_until_complete(self.sut.check_headers())
        Mock.assert_called_with(self.repo.get_header_at_height, 2)
        Mock.assert_called_with(self.repo.delete)
        Mock.assert_called_once_with(self.electrod_loop.call_later, 0, called_coroutine('sync_headers'))
        self.assertEqual(1, len(self.interface.method_calls))
        self.assertEqual(3, len(self.repo.method_calls))
        self.assertEqual(1, len(self.electrod_loop.method_calls))

    def test_local_db_behind_100_headers(self):
        """
        header ff*32 is saved at height 2020
        received a new header at height 2120 with hash aa*32
        chunk from header 2016 is requested
        headers from 2021 to 2120 are saved in the db
        best header is updated at height 2120
        :return:
        """
        raise NotImplementedError

    def received_header_that_doesnt_link_to_previous(self):
        """
        header ff*32 is saved at height 2020
        header aa*32 at height 2021 have prev_block_hash 00*32
        header 2021 is fetched and verified from the network
        header 2020 with hash 00*32 is fetched from 3 peers in the network
        chunk from header 2016 is requested
        headers from 2016 are deleted from the database
        headers from 2016 to 2021 are saved in the db
        best header is updated at height 2021 with hash aa*32
        blockhash ff*32 is saved as orphan and will be ignored to avoid others peers to cause recursive inconsistencies
        """
        raise NotImplementedError
