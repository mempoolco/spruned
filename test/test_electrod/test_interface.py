import asyncio
import unittest
from unittest.mock import Mock, create_autospec
import binascii

import copy

from spruned.application.exceptions import InvalidPOWException
from spruned.daemon.electrod.electrod_connection import ElectrodConnectionPool
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from test.utils import async_coro


class TestElectrodInterface(unittest.TestCase):
    def setUp(self):
        self.connectionpool = create_autospec(ElectrodConnectionPool)
        self.electrod_loop = Mock()
        self.sut = ElectrodInterface(self.connectionpool, self.electrod_loop)
        self.loop = asyncio.get_event_loop()
        self.electrum_header = {
            'block_height': 513526,
            'version': 536870912,
            'prev_block_hash': '000000000000000000323a7adf94b5c7df4221778b502176b998c7a70f0152fe',
            'merkle_root': 'a7f92207352feca838df4293b644fe79b3676487f05972ddbc99274ec92ddb97',
            'timestamp': 1521051443,
            'bits': 391481763,
            'nonce': 2209886775
        }
        self.parsed_header = {
                'block_hash': '0000000000000000001e9a7d5bdb53bf19487d50d9e68e04b7254662d693a6ea',
                'block_height': 513526,
                'header_bytes': b'\x00\x00\x00 \xfeR\x01\x0f\xa7\xc7\x98\xb9v!P\x8bw!B\xdf\xc7\xb5\x94\xdfz:2\x00\x00'
                                b'\x00\x00\x00\x00\x00\x00\x00\x97\xdb-\xc9N\'\x99\xbc\xddrY\xf0\x87dg\xb3y\xfeD\xb6'
                                b'\x93B\xdf8\xa8\xec/5\x07"\xf9\xa73g\xa9Z\xa3\x89U\x1772\xb8\x83',
                'prev_block_hash': '000000000000000000323a7adf94b5c7df4221778b502176b998c7a70f0152fe',
                'timestamp': 1521051443
             }


    def tearDown(self):
        self.connectionpool.reset_mock()
        self.electrod_loop.reset_mock()

    def test_get_header_ok(self):
        peer = Mock()
        self.connectionpool.call.return_value = async_coro((peer, self.electrum_header))
        res = self.loop.run_until_complete(self.sut.get_header(513526))
        self.assertEqual(res, self.parsed_header)
        bitcoind_header = "00000020fe52010fa7c798b97621508b772142dfc7b594df7a3a3200000000000000000097db2dc9" \
                          "4e2799bcdd7259f0876467b379fe44b69342df38a8ec2f350722f9a73367a95aa38955173732b883"
        self.assertEqual(binascii.unhexlify(bitcoind_header), self.parsed_header['header_bytes'])

    def test_get_header_invalid_pow(self):
        peer = Mock()
        peer.disconnect.return_value = 'coroutine'
        electrum_header = {k: v for k, v in self.electrum_header.items()}
        electrum_header.update({'bits': 991481763})  # <- target to the moon
        self.connectionpool.call.return_value = async_coro((peer, electrum_header))
        res = self.loop.run_until_complete(self.sut.get_header(513526))
        self.assertIsNone(res)
        Mock.assert_called_once_with(self.electrod_loop.create_task, 'coroutine')

    def test_get_header_checkpoint_failure(self):
        peer = Mock()
        peer.disconnect.return_value = 'coroutine'
        electrum_header = {k: v for k, v in self.electrum_header.items()}
        electrum_header.update({'block_height': 0})  # <- target to the moon
        self.connectionpool.call.return_value = async_coro((peer, electrum_header))
        res = self.loop.run_until_complete(self.sut.get_header(0))
        self.assertIsNone(res)
        Mock.assert_called_once_with(self.electrod_loop.create_task, 'coroutine')

    def test_subscription_observers(self):
        data = []

        async def callback(peer, header):
            data.append((peer, header))

        peer = Mock()
        observers = []
        self.connectionpool.add_header_observer.side_effect = lambda x: observers.append(x)
        self.sut.add_header_subscribe_callback(callback)
        self.loop.run_until_complete(observers[0](peer, self.electrum_header))
        self.assertEqual(data[0][0], peer)
        self.assertEqual(data[0][1], self.parsed_header)

    def test_subscription_observers_pow_error(self):
        callback = Mock()
        peer = Mock()
        peer.disconnect.return_value = 'coroutine'
        observers = []
        electrum_header = {k: v for k, v in self.electrum_header.items()}
        electrum_header.update({'bits': 991481763})  # <- target to the moon
        self.connectionpool.add_header_observer.side_effect = lambda x: observers.append(x)
        self.connectionpool.call.return_value = async_coro((peer, electrum_header))
        self.sut.add_header_subscribe_callback(callback)
        self.loop.run_until_complete(observers[0](peer, electrum_header))
        res = self.loop.run_until_complete(self.sut.get_header(513526))
        self.assertIsNone(res)
        Mock.assert_called_with(self.electrod_loop.create_task, 'coroutine')
