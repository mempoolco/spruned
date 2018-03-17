import asyncio
import unittest
from unittest.mock import Mock, call, create_autospec
import binascii

import time

from spruned.application.tools import async_delayed_task
from spruned.daemon import exceptions
from spruned.daemon.electrod.electrod_connection import ElectrodConnection, ElectrodConnectionPool
from test.utils import async_coro, coro_call


async def connect(m):
    m._connect.return_value = async_coro(True)
    m.connected = True
    m.protocol = 'protocol'
    return m._connect()


async def disconnect(m):
    m._disconnect.return_value = async_coro(True)
    m.connected = False
    m.protocol = None
    return m._disconnect()


class TestElectrodConnectionPool(unittest.TestCase):
    def setUp(self):
        self.servers = [['hostname{}'.format(x), 's'] for x in range(0, 10)]
        self.electrod_loop = Mock()
        self.delayer = Mock()
        self.electrod_loop = Mock()
        self.network_checker = Mock()
        self.connection_factory = Mock()
        self.sut = ElectrodConnectionPool(
            connections=3,
            loop=self.electrod_loop,
            delayer=self.delayer,
            electrum_servers=self.servers,
            network_checker=self.network_checker,
            connection_factory=self.connection_factory
        )
        self.loop = asyncio.get_event_loop()

    async def stop_keepalive(self, n):
        await asyncio.sleep(n)
        self.sut._keepalive = False

    def test_connect_no_internet_connectivity(self):
        self.sut._sleep_on_no_internet_connectivity = 2
        self.network_checker.return_value = False
        self.loop.run_until_complete(
            asyncio.gather(
                self.stop_keepalive(4.1),
                self.sut.connect()
            )
        )
        self.sut._sleep_on_no_internet_connectivity = 30

        self.assertEqual(0, len(self.sut.connections))
        self.assertEqual(4, self.network_checker.call_count)

    def test_connect_success(self):
        self.sut.loop = self.loop
        self.network_checker.return_value = True
        conn1 = Mock(connected=False)
        conn1.connect = lambda: connect(conn1)
        conn2 = Mock(connected=False)
        conn2.connect = lambda: connect(conn2)
        conn3 = Mock(connected=False)
        conn3.connect = lambda: connect(conn3)
        self.connection_factory.side_effect = [conn1, conn2, conn3]
        on_connected_observer = Mock()
        on_connected_observer.return_value = async_coro(True)
        self.sut.add_on_connected_observer(on_connected_observer)
        self.loop.run_until_complete(
            asyncio.gather(
                self.stop_keepalive(7),
                self.sut.connect()
            )
        )
        self.sut.loop = self.electrod_loop

        for conn in [conn1, conn2, conn3]:
            Mock.assert_called_once(conn.add_on_connect_callback)
            Mock.assert_called_once(conn.add_on_header_callbacks)
            Mock.assert_called_once(conn.add_on_peers_callback)
            Mock.assert_called_once(conn.add_on_error_callback)
            self.assertTrue(conn.connected)
        Mock.assert_called_once(on_connected_observer)
        self.assertEqual(3, len(self.sut.connections))
        self.assertEqual(3, len(self.sut.established_connections))

    def test_connect_too_much_peers(self):
        """
        I didn't tracked with an issue when this happened,
        but it did, maybe asyncio lag\race conditions
        """
        self.sut.loop = self.loop
        self.network_checker.return_value = True
        self.sut._required_connections = 2
        conn1 = Mock(score=10, connected=False)
        conn1.connect = lambda: connect(conn1)
        conn1.disconnect = lambda: disconnect(conn1)
        conn2 = Mock(score=10, connected=False)
        conn1.score = 10
        conn2.connect = lambda: connect(conn2)
        conn2.disconnect = lambda: disconnect(conn2)
        self.connection_factory.side_effect = [conn1, conn2]
        on_connected_observer = Mock()
        on_connected_observer.return_value = async_coro(True)
        self.sut.add_on_connected_observer(on_connected_observer)

        async def _change_behaviour(n):
            await asyncio.sleep(n)
            self.assertEqual(len(self.sut.connections), 2)
            self.sut._required_connections = 1

        self.loop.run_until_complete(
            asyncio.gather(
                self.stop_keepalive(15),
                _change_behaviour(6),
                self.sut.connect()
            )
        )

        self.assertEqual(1, len(self.sut.connections))
        self.assertEqual(1, len(self.sut.established_connections))
        d = 0
        c = 0
        for conn in [conn1, conn2]:
            c += conn._connect.call_count
            d += conn._disconnect.call_count
        self.assertEqual(d, 1)
        self.assertEqual(c, 2)
        self.assertEqual(1, len([c for c in [conn1, conn2] if c.connected]))

    def test_call_corners(self):
        with self.assertRaises(ValueError):
            self.loop.run_until_complete(self.sut.call('cafe', {'par': 'ams'}, get_peer=True, agreement=2))
        with self.assertRaises(ValueError):
            self.sut._required_connections = 2
            self.loop.run_until_complete(
                self.sut.call('cafe', {'par': 'ams'}, agreement=self.sut._required_connections+1)
            )
        with self.assertRaises(exceptions.NoPeersException):
            self.loop.run_until_complete(self.sut.call('cafe', 'babe'))

    def test_call_success(self):
        response = 'some response'
        conn = Mock(connected=True, protocol=True, score=10)
        self.sut._connections = [conn]
        conn.rpc_call.return_value = async_coro(response)
        res = self.loop.run_until_complete(self.sut.call('cafe', 'babe'))
        self.assertEqual(res, response)

        conn.rpc_call.return_value = async_coro(response)
        peer, res = self.loop.run_until_complete(self.sut.call('cafe', 'babe', get_peer=True))
        self.assertEqual(peer, conn)
        self.assertEqual(res, response)

    def test_call_success_multiple_agreement(self):
        response = 'some response'
        conn = Mock(connected=True, protocol=True, score=10)
        conn.rpc_call.return_value = async_coro(response)
        conn2 = Mock(connected=True, protocol=True, score=10)
        conn2.rpc_call.return_value = async_coro(response)
        self.sut._connections = [conn, conn2]
        res = self.loop.run_until_complete(self.sut.call('cafe', 'babe', agreement=2))
        self.assertEqual(res, response)

    def test_call_failure_not_enough_responses(self):
        response = 'some response'
        conn = Mock(connected=True, protocol=True, score=10)
        conn.rpc_call.return_value = async_coro(response)
        conn2 = Mock(connected=True, protocol=True, score=10)
        conn2.rpc_call.return_value = async_coro(None)
        self.sut._connections = [conn, conn2]
        with self.assertRaises(exceptions.ElectrodMissingResponseException):
            self.loop.run_until_complete(self.sut.call('cafe', 'babe', agreement=2))

        conn.rpc_call.return_value = async_coro(response)
        conn2.rpc_call.return_value = async_coro(None)
        self.assertIsNone(
            self.loop.run_until_complete(
                self.sut.call('cafe', 'babe', agreement=2, fail_silent=True)
            )
        )

    def test_call_failure_disagreement_on_responses(self):
        response = 'some response'
        response2 = 'another response'
        conn = Mock(connected=True, protocol=True, score=10)
        conn.rpc_call.return_value = async_coro(response)
        conn2 = Mock(connected=True, protocol=True, score=10)
        conn2.rpc_call.return_value = async_coro(response2)
        self.sut._connections = [conn, conn2]
        with self.assertRaises(exceptions.NoQuorumOnResponsesException):
            self.loop.run_until_complete(self.sut.call('cafe', 'babe', agreement=2))

        conn.rpc_call.return_value = async_coro(response)
        conn2.rpc_call.return_value = async_coro(response2)
        self.assertIsNone(
            self.loop.run_until_complete(
                self.sut.call('cafe', 'babe', agreement=2, fail_silent=True)
            )
        )
