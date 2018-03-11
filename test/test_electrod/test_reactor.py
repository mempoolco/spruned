import asyncio
import unittest
from unittest.mock import Mock, create_autospec
import time

from spruned.application import settings
from spruned.application.abstracts import HeadersRepository
from spruned.daemon import exceptions
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon.electrod.electrod_reactor import ElectrodReactor
from test.utils import async_coro, coro_call, in_range, make_headers
import warnings


class TestElectrodReactor(unittest.TestCase):
    def setUp(self):
        self.repo = create_autospec(HeadersRepository)
        self.interface = create_autospec(ElectrodInterface)
        self.electrod_loop = Mock()
        self.electrod_loop.create_task.side_effect = lambda x: x
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
        test reactor.check_headers method
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
        test reactor.check_headers method
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
        test reactor.on_header method

        network header behind: remote peer outdated, skip
        """
        self.sut.synced = True
        now = int(time.time())
        net_header = {
            'block_height': 1, 'block_hash': 'aa' * 32,
            'timestamp': now - self.sut.new_headers_fallback_poll_interval + 10
        }
        loc_header = {
            'block_height': 2, 'block_hash': 'ff'*32, 'timestamp': now-self.sut.new_headers_fallback_poll_interval+10
        }
        peer = Mock(server_info='mock_peer')
        peer.close.return_value = True
        self.repo.get_best_header.return_value = loc_header
        self.repo.get_header_at_height.return_value = net_header
        self.interface.disconnect_from_peer.return_value = async_coro(True)
        self.loop.run_until_complete(self.sut.on_new_header(peer, net_header))

        Mock.assert_called_once_with(self.repo.get_header_at_height, 1)
        Mock.assert_called_once_with(peer.close)
        self.assertEqual(1, len(self.interface.method_calls))
        self.assertEqual(0, len(self.electrod_loop.method_calls))
        self.assertEqual(2, len(self.repo.method_calls))

    def test_network_equal(self):
        """
        test reactor.on_header

        electrod aligned with remote peers, ensure consistency of received header with local db.
        """
        self.sut.synced = True
        now = int(time.time())
        peer = Mock(server_info='mock_peer')
        net_header = loc_header = {'block_height': 2, 'block_hash': 'ff' * 32, 'timestamp': now-1000}
        self.sut.set_last_processed_header(loc_header)
        self.loop.run_until_complete(self.sut.on_new_header(peer, net_header))
        self.assertEqual(0, len(self.interface.method_calls))
        self.assertEqual(0, len(self.electrod_loop.method_calls))
        self.assertEqual(0, len(self.repo.method_calls))

    def test_received_new_single_header(self):
        """
        test reactor.on_header method

        header ff*32 is saved at height 2020
        received a new header at height 2021 with hash aa*32
        header is saved to disk
        best header is updated at height 2021
        """
        self.sut.synced = False
        peer = Mock(server_info='mock_peer')
        loc_header = {'block_height': 2020, 'block_hash': 'ff' * 32}
        net_header = {'block_height': 2021, 'block_hash': 'aa' * 32, 'prev_block_hash': 'ff'*32, 'header_bytes': b''}
        self.interface.get_header.return_value = async_coro(net_header)

        self.repo.get_best_header.return_value = loc_header

        self.loop.run_until_complete(self.sut.on_new_header(peer, net_header))
        Mock.assert_called_once_with(self.repo.get_best_header)
        Mock.assert_called_once_with(
            self.repo.save_header,
            net_header['block_hash'], net_header['block_height'],
            net_header['header_bytes'], net_header['prev_block_hash']
        )
        self.assertEqual(1, len(self.interface.method_calls))
        self.assertEqual(0, len(self.electrod_loop.method_calls))
        self.assertEqual(2, len(self.repo.method_calls))

    def test_remove_orphan_header_previously_saved(self):
        """
        test reactor.on_header

        header ff*32 is saved at height 2020
        received a new header at height 2020 with hash 00*32
        oops. loop is paused for 20 seconds to allows the network to reorg.
        header at height 2020 is requested to the interface, header 00*32 is returned
        reactor compare headers
        ff*32 is deleted by the repository
        orphaned blockheader is saved somewhere for future usage
        """
        header_timestamp = int(time.time())
        loc_header = {"block_height": 2020, "block_hash": "ff"*32, "timestamp": header_timestamp - 10}
        net_header = {"block_height": 2020, "block_hash": "00"*32, "timestamp": header_timestamp}
        self.sut.synced = True
        self.sut.sleep_time_on_inconsistency = 1
        self.sut.set_last_processed_header(loc_header)

        peer = Mock(server_info='mock_peer')
        self.interface.get_header.return_value = async_coro(net_header)

        self.repo.get_header_at_height(2).return_value = loc_header
        self.repo.get_best_header.return_value = loc_header
        self.repo.get_block_hash.return_value = 'ff' * 32
        self.repo.remove_header_at_height.return_value = loc_header
        self.loop.run_until_complete(self.sut.on_new_header(peer, net_header))

        Mock.assert_called_with(self.repo.get_header_at_height, 2)
        Mock.assert_called_with(self.repo.remove_header_at_height, 2020)
        Mock.assert_not_called(peer.close)

        self.assertEqual(2, len(self.interface.method_calls))
        self.assertEqual(4, len(self.repo.method_calls))
        self.assertEqual(0, len(self.electrod_loop.method_calls))
        self.assertFalse(self.sut.synced)
        self.assertIn(loc_header, self.sut.orphans_headers)

    def test_local_db_behind_100_headers(self):
        """
        test reactor.on_new_header

        header ff*32 is saved at height 2020
        received a new header at height 2120 with hash aa*32
        chunk from header 2016 is requested
        headers from 2021 to 2120 are saved in the db
        best header is updated at height 2120
        :return:
        """
        header_timestamp = int(time.time())
        peer = Mock(server_info='mock_peer')
        loc_header = {"block_height": 2020, "block_hash": "ff" * 32, "timestamp": header_timestamp - 6000}
        net_header = {"block_height": 2120, "block_hash": "aa" * 32, "timestamp": header_timestamp}
        self.sut.synced = True
        self.sut.set_last_processed_header(loc_header)
        self.repo.get_best_header.return_value = loc_header
        _headers = make_headers(2017, 2120, '00'*32)
        self.interface.get_headers_in_range_from_chunks.side_effect = [async_coro(_headers), async_coro(None)]
        self.interface.get_header.return_value = async_coro(net_header)
        self.repo.save_headers.side_effect = lambda x, **k: x

        self.loop.run_until_complete(self.sut.on_new_header(peer, net_header))

        Mock.assert_called_with(self.repo.save_headers, [h for h in _headers if h['block_height'] > 2020])
        Mock.assert_not_called(peer.close)
        self.assertEqual(self.sut._last_processed_header, _headers[-1])
        self.assertEqual(self.sut.synced, True)
        self.assertEqual(1, len(self.interface.method_calls))
        self.assertEqual(2, len(self.repo.method_calls))
        self.assertEqual(0, len(self.electrod_loop.method_calls))

    def test_received_header_that_doesnt_link_to_previous(self):
        """
        on_new_header

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
        header_timestamp = int(time.time())
        peer = Mock(server_info='mock_peer')
        loc_header = {"block_height": 2020, "block_hash": "ff" * 32, "timestamp": header_timestamp - 1000}
        net_header = {
            "block_height": 2021, 
            "block_hash": "aa" * 32, 
            "timestamp": header_timestamp, 
            "prev_block_hash": "00"*32,
            "header_bytes": b""
        }
        self.sut.synced = True
        self.sut.set_last_processed_header(loc_header)
        self.interface.get_header.return_value = async_coro(net_header)
        self.repo.get_best_header.return_value = loc_header

        self.repo.save_header.side_effect = [exceptions.HeadersInconsistencyException]
        self.loop.run_until_complete(self.sut.on_new_header(peer, net_header))
        Mock.assert_called_once_with(self.repo.remove_headers_after_height, 2016)
        Mock.assert_called(self.repo.get_best_header)
        Mock.assert_called_once_with(self.interface.get_header, 2021, fail_silent_out_of_range=True)
        Mock.assert_called_once_with(self.repo.remove_headers_after_height, 2016)

        self.assertIsNone(self.sut._last_processed_header)
        self.assertEqual(1, len(self.interface.method_calls), msg=str(self.interface.method_calls))
        self.assertEqual(4, len(self.repo.method_calls), msg=str(self.repo.method_calls))
        self.assertEqual(0, len(self.electrod_loop.method_calls), msg=str(self.electrod_loop.method_calls))
        self.assertFalse(self.sut.synced)
        self.assertFalse(self.sut.lock.locked())

    def test_no_local_headers(self):
        """
        a new header is received, best_height is 3000
        there is no local header
        the chunk 0 is requested, but there are no peers available due race condition
        then the chunk 0 is fetched and saved
        then the chunk 1 is fetched and saved
        new height is 3000
        reactor is in sync with the network
        """
        header_timestamp = int(time.time())
        net_header = {
            "block_height": 3000,
            "block_hash": "cc" * 32,
            "timestamp": header_timestamp,
            "prev_block_hash": "00" * 32,
            "header_bytes": b"0"*80
        }
        peer = Mock(server_info='mock_peer')
        loc_header = None
        self.repo.get_best_header.return_value = loc_header
        _chunk_1 = make_headers(0, 2015, settings.CHECKPOINTS[0])
        _chunk_2 = make_headers(2016, 2999, _chunk_1[-1]['block_height'])
        _chunk_2.append(net_header)

        self.interface.get_headers_in_range_from_chunks.side_effect = [
            exceptions.NoPeersException,
            async_coro(_chunk_1),
            async_coro(_chunk_2)
        ]
        self.interface.get_header.return_value = async_coro(net_header)
        self.repo.save_headers.side_effect = lambda x, **k: x

        self.loop.run_until_complete(self.sut.on_new_header(peer, net_header))
        self.assertEqual(self.sut._last_processed_header, net_header)
        self.assertTrue(self.sut.synced)
        self.assertEqual(3, len(self.interface.method_calls))
        self.assertEqual(4, len(self.repo.method_calls))
        self.assertEqual(0, len(self.electrod_loop.method_calls))
