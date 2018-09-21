import asyncio
from unittest import TestCase
from unittest.mock import Mock, call
from spruned.daemon.bitcoin_p2p.p2p_connection import P2PConnectionPool

from test.utils import async_coro, coro_call


class TestP2PConnectionPool(TestCase):
    def setUp(self):
        self.loopmock = Mock()
        self.online_checker = Mock()
        self.delayer = Mock()
        self.port = 8333
        self.sut = P2PConnectionPool(
            network_checker=self.online_checker, delayer=self.delayer,
            loop=self.loopmock, proxy=False, sleep_no_internet=1, connections=2
        )
        self.loop = asyncio.get_event_loop()
        self.peers = [['cafe', 123], ['babe', 123], ['eta', 123], ['beta', 123]]

    def test_connect_ok(self):
        async def parallel():
            await asyncio.sleep(3)
            for peer in self.peers:
                self.sut.add_peer(peer)

            await asyncio.sleep(5)
            self.sut._keepalive = False

        self.online_checker.side_effect = [async_coro(False), async_coro(True)]
        self.loop.run_until_complete(
            asyncio.gather(
                parallel(),
                self.sut.connect()
            )
        )
        Mock.assert_has_calls(
            self.loopmock.create_task,
            calls=[
                call(coro_call('_connect_peer')), call(coro_call('_connect_peer'))
            ]
        )
