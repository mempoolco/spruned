import asyncio
import unittest
from unittest.mock import Mock, call, ANY

import time

from spruned.daemon import exceptions
from spruned.daemon.electrod.electrod_connection import ElectrodConnectionPool
from test.utils import async_coro


async def connect(m):
    m._connect.return_value = True
    m.connected = True
    m.protocol = 'protocol'
    return m._connect()


async def disconnect(m):
    m._disconnect.return_value = True
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
        self.servers_storage = Mock()
        self.sut = ElectrodConnectionPool(
            connections=3,
            loop=self.electrod_loop,
            delayer=self.delayer,
            peers=self.servers,
            network_checker=self.network_checker,
            connection_factory=self.connection_factory,
            servers_storage=self.servers_storage
        )
        self.loop = asyncio.get_event_loop()

    async def stop_keepalive(self, n):
        await asyncio.sleep(n)
        self.sut._keepalive = False

    def test_connect_no_internet_connectivity(self):
        self.sut._sleep_on_no_internet_connectivity = 2
        self.network_checker.return_value = async_coro(True)
        self.loop.run_until_complete(
            asyncio.gather(
                self.stop_keepalive(4.1),
                self.sut.connect()
            )
        )
        self.sut._sleep_on_no_internet_connectivity = 30

        self.assertEqual(0, len(self.sut.connections))
        self.assertEqual(1, self.network_checker.call_count)

    def test_connect_success(self):
        self.sut.loop = self.loop
        self.network_checker.return_value = async_coro(True)
        conn1 = Mock(connected=False, score=0)
        conn1.connect = lambda: connect(conn1)
        conn2 = Mock(connected=False, score=0)
        conn2.connect = lambda: connect(conn2)
        conn3 = Mock(connected=False, score=0)
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
            self.assertEqual(conn.add_on_connect_callback.call_count, 1)
            self.assertEqual(conn.add_on_header_callbacks.call_count, 1)
            self.assertEqual(conn.add_on_peers_callback.call_count, 1)
            self.assertEqual(conn.add_on_error_callback.call_count, 1)
            self.assertTrue(conn.connected)
        self.assertEqual(on_connected_observer.call_count, 1)
        self.assertEqual(3, len(self.sut.connections))
        self.assertEqual(3, len(self.sut.established_connections))

    def test_connect_too_much_peers(self):
        """
        I didn't tracked with an issue when this happened,
        but it did, maybe asyncio lag\race conditions
        """
        self.sut.loop = self.loop
        self.network_checker.return_value = async_coro(True)
        self.sut._required_connections = 2
        conn1 = Mock(score=10, connected=False, start_score=10)
        conn1.connect = lambda: connect(conn1)
        conn1.disconnect = lambda: disconnect(conn1)
        conn2 = Mock(score=10, connected=False, start_score=10)
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

    def test_call_missing_response(self):
        conn = Mock(connected=True, protocol=True, score=10)
        conn2 = Mock(connected=True, protocol=True, score=10)
        conn.rpc_call.return_value = async_coro(None)
        conn2.rpc_call.return_value = async_coro(None)
        self.sut._connections = [conn, conn2]
        with self.assertRaises(exceptions.ElectrodMissingResponseException):
            self.loop.run_until_complete(
                self.sut.call('cafe', 'babe', agreement=2)
            )

    def test_corners(self):
        s = [s for s in self.sut._peers]
        self.sut._peers = []
        with self.assertRaises(exceptions.NoServersException):
            self.sut._pick_peer()
        with self.assertRaises(exceptions.NoServersException):
            self.sut._pick_multiple_peers(2)
        self.sut._peers = s
        with self.assertRaises(exceptions.NoPeersException):
            self.sut._pick_connection()
        with self.assertRaises(exceptions.NoPeersException):
            self.sut._pick_multiple_connections(2)
        self.assertIsNone(
            self.sut._pick_connection(fail_silent=True)
        )
        self.sut._peers = ['cafebabe']
        self.sut._connections.append(Mock(hostname='cafebabe', connected=True, score=1))
        with self.assertRaises(exceptions.NoServersException):
            self.sut._pick_peer()
        with self.assertRaises(exceptions.NoServersException):
            self.sut._pick_multiple_peers(1)

    def test__handle_peer_error_disconnected(self):
        conn = Mock(connected=False)
        res = self.loop.run_until_complete(self.sut._handle_peer_error(conn))
        self.assertIsNone(res)

    def test_handle_peer_error_noscore(self):
        conn = Mock(connected=True, score=0)
        conn.disconnect.return_value = 'disconnect'
        self.delayer.return_value = 'delayer'
        res = self.loop.run_until_complete(self.sut._handle_peer_error(conn))
        self.assertIsNone(res)
        Mock.assert_called_with(self.electrod_loop.create_task, 'delayer')
        Mock.assert_called_with(self.delayer, 'disconnect')

    def test_handle_peer_error_ping_timeout(self):
        conn = Mock(connected=True, score=10)
        conn.ping.return_value = async_coro(None)
        conn.disconnect.return_value = 'disconnect'
        self.delayer.return_value = 'delayer'

        res = self.loop.run_until_complete(self.sut._handle_peer_error(conn))
        self.assertIsNone(res)
        Mock.assert_called_with(self.electrod_loop.create_task, 'delayer')
        Mock.assert_called_with(self.delayer, 'disconnect')

    def test_on_connected_callback(self):
        peer = Mock()
        cob = Mock()
        self.network_checker.return_value = async_coro(True)
        self.sut.add_on_connected_observer(cob)
        peer.subscribe.return_value = 'subscriberrr'
        self.delayer.return_value = 'delayerrr'
        self.loop.run_until_complete(self.sut.on_peer_connected(peer))
        Mock.assert_called_with(
            peer.subscribe,
            'blockchain.headers.subscribe',
            self.sut.on_peer_received_header,
            self.sut.on_peer_received_header,
        )
        Mock.assert_has_calls(
            self.electrod_loop.create_task,
            calls=[
                call('delayerrr'),
                call(ANY)
            ]
        )
        Mock.assert_called_once_with(self.delayer, 'subscriberrr')

    def test_on_headers_callback(self):
        peer = Mock(last_header='header')
        hob = Mock()
        hob.return_value = 'observing'
        self.delayer.return_value = 'delayerr'
        self.network_checker.return_value = async_coro(True)
        self.sut.add_header_observer(hob)
        self.loop.run_until_complete(self.sut.on_peer_received_header(peer))
        Mock.assert_called_once_with(self.electrod_loop.create_task, 'delayerr')
        Mock.assert_called_once_with(hob, peer, 'header')
        Mock.assert_called_once_with(self.delayer, 'observing')

    def test_on_peer_error(self):
        peer = Mock(is_online=True, connected=False, _errors=[])
        peer.add_error = lambda *x: peer._errors.append(x[0]) if x else peer._errors.append(int(time.time()))
        self.loop.run_until_complete(self.sut.on_peer_error(peer))
        self.assertEqual(len(peer._errors), 1)

    def test_on_peer_error_during_connection(self):
        peer = Mock(is_online=True, connected=False, _errors=[])
        peer.add_error = lambda *x: peer._errors.append(x[0]) if x else peer._errors.append(int(time.time()))
        self.network_checker.return_value = async_coro(False)
        self.loop.run_until_complete(self.sut.on_peer_error(peer, error_type='connect'))
        self.assertEqual(len(peer._errors), 0)

        self.network_checker.return_value = async_coro(True)
        self.loop.run_until_complete(self.sut.on_peer_error(peer, error_type='connect'))
        self.assertEqual(len(peer._errors), 1)
