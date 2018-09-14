import asyncio
from unittest import TestCase
from unittest.mock import Mock, call, ANY

from spruned.dependencies.pycoinnet.networks import MAINNET

from spruned.daemon.bitcoin_p2p.p2p_interface import P2PInterface
from test.utils import async_coro


class TestP2PInterface(TestCase):
    def setUp(self):
        self.pool = Mock()
        self.loopmock = Mock()
        self.peers_bootstrapper = Mock()
        self.sut = P2PInterface(self.pool, loop=self.loopmock, peers_bootstrapper=self.peers_bootstrapper)
        self.loop = asyncio.get_event_loop()

    def test_start(self):
        self.peers_bootstrapper.return_value = async_coro((('1.2.3.4', 8333), ('1.2.3.5', 8333)))

        self.loop.run_until_complete(self.sut.start())
        self.assertEqual(self.pool.add_on_connected_observer.call_count, 1)
        Mock.assert_called_with(self.peers_bootstrapper, MAINNET)
        Mock.assert_has_calls(
            self.pool.add_peer,
            calls=[
                call(('1.2.3.4', 8333)),
                call(('1.2.3.5', 8333))
            ]
        )
        Mock.assert_called_once_with(self.pool.connect)
        self.assertEqual(self.loopmock.create_task.call_count, 1)
        self.sut.set_bootstrap_status(10)
        self.assertEqual(self.sut.bootstrap_status, 10)

    def test_get_block(self):
        block = b'block'
        self.pool.get.return_value = async_coro(block)
        response = self.loop.run_until_complete(self.sut.get_block('aa'*32))
        self.assertEqual(
            response,
            {
                "block_hash": "aa"*32,
                "header_bytes": b"block",
                "block_bytes": b"block"
            }
        )

    def test_get_blocks(self):
        block = b'block'
        self.pool.get.return_value = async_coro(block)
        response = self.loop.run_until_complete(self.sut.get_blocks('aa'*32))
        self.assertEqual(
            {
                "aa" * 32:
                    {
                        "block_hash": "aa"*32,
                        "header_bytes": b"block",
                        "block_bytes": b"block"
                    }
            },
            response
        )
