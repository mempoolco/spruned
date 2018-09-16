import asyncio
import unittest
from unittest.mock import Mock, create_autospec, call
import binascii
from spruned.daemon.electrod.electrod_connection import ElectrodConnectionPool, ElectrodConnection
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon.exceptions import ElectrodMissingResponseException
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
        Mock.assert_called_with(self.connectionpool.call, 'blockchain.block.get_header', 0, get_peer=True)

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

    def test_get_headers_no_response(self):
        self.connectionpool.call.side_effect = [
            ElectrodMissingResponseException, ElectrodMissingResponseException, async_coro(('a', self.electrum_header))
        ]
        with self.assertRaises(ElectrodMissingResponseException):
            self.loop.run_until_complete(self.sut.get_header(10))
        self.assertIsNone(self.loop.run_until_complete(self.sut.get_header(10, fail_silent_out_of_range=True)))
        peer, res = self.loop.run_until_complete(self.sut.get_header(10, get_peer=1))
        self.assertEqual(peer, 'a')
        self.assertEqual(res, self.parsed_header)
        Mock.assert_called_with(self.connectionpool.call, 'blockchain.block.get_header', 10, get_peer=True)

    def test_var_methods(self):
        self.electrod_loop.create_task.return_value = 1
        self.loop.run_until_complete(self.sut.start())
        peer = create_autospec(ElectrodConnection)
        self.loop.run_until_complete(self.sut.disconnect_from_peer(peer))
        Mock.assert_called_with(peer.disconnect)
        self.assertEqual(2, len(self.electrod_loop.method_calls))
        self.electrod_loop.reset_mock()

        self.sut.add_on_connected_callback('callback')
        self.connectionpool.add_on_connected_observer.return_value = True
        Mock.assert_called_with(
            self.connectionpool.add_on_connected_observer,
            'callback'
        )

        self.connectionpool.call.side_effect = [
            async_coro('cafe'),
            async_coro({'hex': 'rawtx'}),
            async_coro('chunk_of_headers'),
            async_coro({'list': 'unspents'}),
            async_coro({'txs': 'list'}),
            async_coro({'fee': 'rate'})
        ]
        peer = Mock()
        self.connectionpool.on_peer_error.return_value = async_coro(lambda x: x.close())
        self.loop.run_until_complete(self.sut.getrawtransaction('cafebabe'))
        self.loop.run_until_complete(self.sut.getrawtransaction('cafebabe', verbose=True))
        self.loop.run_until_complete(self.sut.get_chunk(1))
        self.loop.run_until_complete(self.sut.listunspents_by_address('address'))
        self.loop.run_until_complete(self.sut.getaddresshistory('scripthash'))
        self.loop.run_until_complete(self.sut.handle_peer_error(peer))
        Mock.assert_has_calls(
            self.connectionpool.call,
            calls=[
                call('blockchain.transaction.get', 'cafebabe', 0),
                call('blockchain.transaction.get', 'cafebabe', 1),
                call('blockchain.block.get_chunk', 1, get_peer=False),
                call('blockchain.address.listunspent', 'address'),
                call('blockchain.address.get_history', 'scripthash'),
            ]
        )
        Mock.assert_called_with(self.connectionpool.on_peer_error, peer)

    def test_get_headers_in_range(self):

        async def get_chunk(method, chunk, get_peer=False):
            self.assertEqual(method, 'blockchain.block.get_chunk')
            bitcoind_header = "00000020fe52010fa7c798b97621508b772142dfc7b594df7a3a3200000000000000000097db2dc9" \
                              "4e2799bcdd7259f0876467b379fe44b69342df38a8ec2f350722f9a73367a95aa38955173732b883"
            i = {1: 2016, 2: 1024}
            return bitcoind_header * i[chunk]

        self.connectionpool.call.side_effect = get_chunk
        res = self.loop.run_until_complete(self.sut.get_headers_in_range_from_chunks(1, 3))
        Mock.assert_has_calls(
            self.connectionpool.call,
            calls=[call('blockchain.block.get_chunk', 1, get_peer=False),
                   call('blockchain.block.get_chunk', 2, get_peer=False)],
            any_order=True
        )
        i = 0
        for header in res:
            self.assertEqual(header.get('block_height'), i+2016)
            header['block_height'] = 513526
            i += 1
            header_from_chunk = {
                'bits': 391481763,
                'block_hash': '0000000000000000001e9a7d5bdb53bf19487d50d9e68e04b7254662d693a6ea',
                'block_height': 513526,
                'header_bytes': b'\x00\x00\x00 \xfeR\x01\x0f\xa7\xc7\x98\xb9v!P\x8bw!B\xdf'
                b'\xc7\xb5\x94\xdfz:2\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                b"\x97\xdb-\xc9N'\x99\xbc\xddrY\xf0\x87dg\xb3y\xfeD\xb6"
                b'\x93B\xdf8\xa8\xec/5\x07"\xf9\xa73g\xa9Z\xa3\x89U\x17'
                b'72\xb8\x83',
                'merkle_root': 'a7f92207352feca838df4293b644fe79b3676487f05972ddbc99274ec92ddb97',
                'nonce': 2209886775,
                'prev_block_hash': '000000000000000000323a7adf94b5c7df4221778b502176b998c7a70f0152fe',
                'timestamp': 1521051443,
                'version': 536870912
            }
            self.assertEqual(header, header_from_chunk, msg='%s %s' % (header_from_chunk, header))
        self.assertEqual(len(res), 3040)

    def test_get_chunks_no_chunk(self):
        self.connectionpool.call.return_value = async_coro(None)
        self.assertIsNone(self.loop.run_until_complete(self.sut.get_headers_from_chunk(1)))

    def test_get_headers_in_range_ok(self):
        peer = Mock()
        self.connectionpool.call.side_effect = [
            async_coro((peer, self.electrum_header)),
            async_coro((peer, self.electrum_header))
        ]
        res = self.loop.run_until_complete(self.sut.get_headers_in_range(1, 3))
        self.assertEqual(res, [self.parsed_header, self.parsed_header])
