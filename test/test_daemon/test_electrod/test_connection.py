import asyncio
import unittest
from unittest.mock import Mock
import binascii

import time

from spruned.application.tools import async_delayed_task
from spruned.daemon.electrod.electrod_connection import ElectrodConnection
from test.utils import async_coro, coro_call


class TestElectrodConnection(unittest.TestCase):

    def setUp(self):
        self.checker = Mock().checker
        self.checker.return_value = True
        self.client = Mock()
        self.client_factory = lambda: self.client
        self.serverinfo = Mock()
        self.electrod_loop = Mock()
        self.delayer = Mock()
        self.sut = ElectrodConnection(
            'hostname', 's', client=self.client_factory, expire_errors_after=3,
            is_online_checker=self.checker, serverinfo=self.serverinfo, loop=self.electrod_loop,
            delayer=self.delayer
        )
        print(self.sut.proxy)
        self.assertEqual(self.sut.start_score, self.sut._start_score)
        self.loop = asyncio.get_event_loop()

    def tearDown(self):
        self.client.reset_mock()

    def test_errors_score(self):
        self.loop.run_until_complete(
            asyncio.gather(
                self.sut.on_error('error1'),
                self.sut.on_error('error1'),
                self.sut.on_error('error1')
            )
        )
        self.assertEqual(self.sut.score, 7)
        time.sleep(3.01)
        self.assertEqual(self.sut.score, 10)

    def test_connect_success(self):
        self.serverinfo.return_value = 'server info'
        self.client.connect.return_value = async_coro(None)
        self.client.server_version = 'ElectrumX 1.2'
        self.client.RPC.return_value = async_coro(
            {'blockhash': '00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048'}
        )
        callback = Mock()
        callback.return_value = async_coro(True)
        self.sut.add_on_connect_callback(callback)

        self.loop.run_until_complete(self.sut.connect())
        self.assertTrue(self.sut.version, 'ElectrumX 1.2')
        Mock.assert_called_once_with(
            self.client.connect,
            'server info',
            disconnect_callback=self.sut.on_connectrum_disconnect,
            disable_cert_verify=True,
            proxy=self.sut.proxy,
            ignore_version=False,
            short_term=False
        )
        Mock.assert_called_once_with(
            self.serverinfo,
            self.sut.nickname, hostname='hostname', ports='s', version='1.2'
        )
        self.assertEqual(8, len(binascii.unhexlify(self.sut.nickname)))
        self.assertEqual(callback.call_count, 1)

    def test_disconnection(self):
        self.client.protocol = True
        self.client.close.side_effect = ConnectionError
        self.loop.run_until_complete(self.sut.disconnect())
        self.assertFalse(self.sut.connected)
        Mock.assert_called_once_with(self.client.close)

    def test_connect_failure(self):
        called = False

        async def connfalse(peer, error_type=None):
            nonlocal called
            called = True
            self.assertEqual(error_type, 'connect')
            self.checker.return_value = False

        self.client.connect.side_effect = ConnectionError
        self.assertTrue(self.sut.is_online())
        self.sut.add_on_error_callback(connfalse)
        self.sut.loop = self.loop
        self.loop.run_until_complete(self.sut.connect())
        self.assertIsNone(self.sut._version)
        self.assertTrue(called)
        self.assertFalse(self.sut.is_online())

    def test_connection_timeout(self):
        self.delayer.return_value = 'delayed'
        self.client.connect.return_value = asyncio.sleep(2)
        self.sut._timeout = 1
        self.loop.run_until_complete(self.sut.connect())
        self.assertIsNone(self.sut._version)
        self.assertEqual(1, len(self.sut.errors))
        self.assertEqual(9, self.sut.score)

    def test_rpc_call_success(self):
        self.client.RPC.return_value = async_coro(True)
        res = self.loop.run_until_complete(self.sut.rpc_call('method', ('cafe', 'babe')))
        Mock.assert_called_once_with(
            self.client.RPC,
            'method', 'cafe', 'babe'
        )
        self.assertEqual(res, True)

    def test_rpc_call_error(self):
        self.delayer.return_value = 'delayed'
        self.client.RPC.return_value = ConnectionError
        res = self.loop.run_until_complete(self.sut.rpc_call('method', ('cafe', 'babe')))
        self.assertEqual(res, None)
        Mock.assert_called_once_with(self.electrod_loop.create_task, 'delayed')
        Mock.assert_called_once_with(self.delayer, coro_call('on_error'))

    def test_ping_success(self):
        self.client.RPC.return_value = asyncio.gather(asyncio.sleep(1.1), async_coro('ElectrumX 1.2'))
        res = self.loop.run_until_complete(self.sut.ping())
        self.assertEqual(1.1 < res < 1.15, True)

    def test_ping_timeout(self):
        self.client.RPC.return_value = asyncio.sleep(4)
        res = self.loop.run_until_complete(self.sut.ping(timeout=1))
        self.assertIsNone(res)

    def test_subscribe_and_fail(self):
        queue = Mock()
        queue.get.side_effect = [async_coro([{'block_height': '2'}]), ConnectionError]
        future = {'block_height': '1'}
        self.client.subscribe.return_value = async_coro(future), queue
        sub_called = False

        async def on_subscription(*a):
            nonlocal sub_called
            self.assertEqual(a[0]._last_header, {'block_height': '1'})
            sub_called = True

        self.sut.loop = self.loop
        self.sut.delayer = async_delayed_task
        self.loop.run_until_complete(self.sut.subscribe('channel', on_subscription, lambda *a: async_coro(True)))
        Mock.assert_not_called(self.electrod_loop.create_task)
        self.assertTrue(sub_called)
        self.sut._last_header = {'block_height': '2'}

    def test_subscribe_error(self):
        self.sut.loop = self.electrod_loop
        self.delayer.return_value = 'delayer'
        self.client.subscribe.side_effect = ConnectionError
        self.loop.run_until_complete(self.sut.subscribe('cafe', 'babe', 'c0ca'))
        Mock.assert_called_with(self.electrod_loop.create_task, 'delayer')
        Mock.assert_called_with(self.delayer, coro_call('on_error'))

    def test_callbacks(self):
        hcb = Mock(return_value=async_coro(True))
        ccb = Mock(return_value=async_coro(True))
        dcb = Mock(return_value=async_coro(True))
        pcb = Mock(return_value=async_coro(True))
        ecb = Mock(return_value=async_coro(True))
        self.sut.add_on_header_callbacks(hcb)
        self.sut.add_on_error_callback(ecb)
        self.sut.add_on_connect_callback(ccb)
        self.sut.add_on_disconnect_callback(dcb)
        self.sut.add_on_peers_callback(pcb)
        self.loop.run_until_complete(
            asyncio.gather(
                self.sut.on_header('header'),
                self.sut.on_connect(),
                self.sut.on_error('error'),
                self.sut.on_peers()
            )
        )
        self.sut.on_connectrum_disconnect()
        for m in [hcb, ccb, dcb, pcb]:
            Mock.assert_called_with(m, self.sut)
        Mock.assert_called_with(ecb, self.sut, error_type='error')
        self.assertEqual(self.sut.last_header, 'header')
