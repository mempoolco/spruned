import asyncio
import unittest
from unittest.mock import Mock, create_autospec

import time

from spruned.application.abstracts import HeadersRepository
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon.electrod.electrod_reactor import ElectrodReactor
from test.utils import async_coro, coro_call, in_range
import warnings


class TestElectrodReactor(unittest.TestCase):
    def setUp(self):
        self.repo = create_autospec(HeadersRepository)
        self.interface = create_autospec(ElectrodInterface)
        self.electrod_loop = Mock()
        self.electrod_loop.create_task.side_effect: lambda x: x
        self.delay_task_runner = Mock()
        self.sut = ElectrodReactor(
            self.repo, self.interface, loop=self.electrod_loop, delayed_task=self.delay_task_runner
        )
        self.loop = asyncio.get_event_loop()
        warnings.filterwarnings("ignore")

    def tearDown(self):
        self.repo.reset_mock()
        self.interface.reset_mock()
        self.electrod_loop.reset_mock()

    def test_last_header_received_less_than_min_polling_interval(self):
        """
        last header is saved less than polling interval value (default: 660)
        """
        header_timestamp = int(time.time()) - 100
        loc_header = {"block_height": 1, "block_hash": "ff"*32, "timestamp": header_timestamp}
        self.interface.get_header.return_value = async_coro(None)
        self.sut.synced = True
        self.sut.set_last_processed_header(loc_header)
        self.loop.run_until_complete(self.sut.check_headers())
        self.assertFalse(self.sut.lock.locked())

        Mock.assert_called_once_with(self.delay_task_runner, coro_call('check_headers'), in_range(559, 560))
        self.assertEqual(0, len(self.interface.method_calls))
        self.assertEqual(1, len(self.electrod_loop.method_calls))
        self.assertEqual(0, len(self.repo.method_calls))

    def test_no_new_network_best_header(self):
        """
        interface didn't returned any best header. will try again in
        """
        header_timestamp = int(time.time()) - self.sut.new_headers_fallback_poll_interval - 1
        loc_header = {"block_height": 1, "block_hash": "ff" * 32, "timestamp": header_timestamp}
        self.interface.get_header.return_value = async_coro(None)
        self.sut.synced = True
        self.sut.set_last_processed_header(loc_header)
        self.loop.run_until_complete(self.sut.check_headers())
        self.assertFalse(self.sut.lock.locked())

        Mock.assert_called_once_with(self.delay_task_runner, coro_call('check_headers'), 660)
        Mock.assert_called_with(self.interface.get_header, 2, fail_silent_out_of_range=True)
        Mock.assert_called_once_with(self.electrod_loop.create_task, self.delay_task_runner())

        self.assertEqual(1, len(self.interface.method_calls))
        self.assertEqual(1, len(self.electrod_loop.method_calls))
        self.assertEqual(0, len(self.repo.method_calls))

    def test_network_header_behind(self):
        """
        network header behind: remote peer outdated, skip
        """
        loc_header = {'block_height': 2, 'block_hash': 'ff'*32}
        self.repo.get_best_header.return_value = loc_header
        self.repo.get_header_at_height.return_value = loc_header
        self.loop.run_until_complete(self.sut.check_headers())

        Mock.assert_not_called(self.repo.get_header_at_height)
        Mock.assert_called_once_with(self.delay_task_runner, coro_call('check_headers'), 120)
        Mock.assert_called_once_with(self.electrod_loop.create_task, self.delay_task_runner())

        self.assertEqual(0, len(self.interface.method_calls))
        self.assertEqual(1, len(self.electrod_loop.method_calls))
        self.assertEqual(0, len(self.repo.method_calls))

    def test_network_equal(self):
        """
        electrod aligned with remote peers, ensure consistency of received header with local db.
        """
        loc_header = {'block_height': 2, 'block_hash': 'ff' * 32}
        self.repo.get_header_at_height(2).return_value = loc_header
        self.loop.run_until_complete(self.sut.check_headers())

        Mock.assert_called_with(self.repo.get_header_at_height, 2)
        Mock.assert_called_once_with(self.delay_task_runner, coro_call('check_headers'), 120)
        Mock.assert_called_once_with(self.repo.get_header_at_height, 2)

        self.assertEqual(0, len(self.interface.method_calls))
        self.assertEqual(1, len(self.electrod_loop.method_calls))
        self.assertEqual(1, len(self.repo.method_calls))

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
        Mock.assert_called_once_with(self.electrod_loop.call_later, 0, coro_call('sync_headers'))
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
