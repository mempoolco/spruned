import asyncio
from unittest import TestCase
from unittest.mock import Mock

import time
from spruned.dependencies.pycoinnet.pycoin.InvItem import ITEM_TYPE_TX

from spruned.daemon.bitcoin_p2p.p2p_connection import P2PConnection
from test.utils import async_coro


class TestP2PConnection(TestCase):
    def setUp(self):
        self.loopmock = Mock()
        self.online_checker = Mock()
        self.delayer = Mock()
        self._peer_name = ('127.0.0.1', 8333, 'peer_name')
        self.peer_factory = Mock()
        self.peer_factory()._reader = Mock(_transport=Mock())
        self.peer_factory()._reader._transport.get_extra_info.return_value = self._peer_name
        self.connector = Mock()
        self.hostname = 'hostname'
        self.port = 8333
        self.sut = P2PConnection(
            self.hostname, self.port, loop=self.loopmock,
            is_online_checker=self.online_checker, delayer=self.delayer,
            call_timeout=3, connector=self.connector, peer=self.peer_factory
        )
        self.loop = asyncio.get_event_loop()

    def test_connect_ok(self):
        callback = Mock()
        callback_blocks = Mock()
        self.sut.best_header = {'block_height': 1}
        self.sut.add_on_blocks_callback(callback_blocks)
        self.sut.add_on_connect_callback(callback)

        self.sut.best_header = {'block_height': 1}
        reader, writer = Mock(), Mock()
        self.peer_factory().perform_handshake.return_value = async_coro(
            {
                'subversion': b'the peer version answer',
                'last_block_index': 1
            }
        )
        self.connector.return_value = async_coro((reader, writer))
        self.peer_factory().next_message.return_value = async_coro(None)
        self.loop.run_until_complete(self.sut.connect())
        self.assertEqual(self.sut._version, {'subversion': b'the peer version answer', 'last_block_index': 1})
        self.assertEqual(len(self.loopmock.method_calls), 1)
        Mock.assert_not_called(callback_blocks)
        self.assertTrue(self.sut.connected)

    def test_connect_exception(self):
        self.connector.side_effect = ValueError
        self.loop.run_until_complete(self.sut.connect())
        self.assertIsNone(self.sut._version)

    def test_disconnect(self):
        self.loop.run_until_complete(self.sut.disconnect())
        peer = Mock()
        self.sut.peer = peer
        self.sut.peer.close.return_value = True
        self.loop.run_until_complete(self.sut.disconnect())
        Mock.assert_called_once_with(peer.close)
        self.assertIsNone(self.sut.peer)

    def test_on_events(self):
        called = False

        async def txs_callback(*a, **kw):
            nonlocal called
            called = True

        async def wait():
            nonlocal called
            now = int(time.time())
            while not called:
                await asyncio.sleep(2)
                if int(time.time()) - now > 5:
                    raise AssertionError('Timeout!')

        async def start():
            self.sut._on_inv('inv', 'tx', {'items': [item]})

        item = Mock(item_type=ITEM_TYPE_TX)
        self.sut.loop = self.loop
        self.sut.add_on_transaction_hash_callback(txs_callback)
        self.loop.run_until_complete(asyncio.gather(
            wait(), start()
        ))
        self.sut.loop = self.loopmock
        self.assertTrue(called)

    def test_on_ping(self):
        self.sut.peer = Mock()
        self.sut._on_ping('ping', 'ping', {'nonce': 'cafe'})
        Mock.assert_called_once_with(self.sut.peer.send_msg, 'pong', nonce='cafe')
