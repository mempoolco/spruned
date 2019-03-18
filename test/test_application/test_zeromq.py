import signal

import random
from unittest import TestCase
from unittest.mock import Mock, create_autospec
import sys
import async_timeout
import binascii

import time
from zmq.asyncio import Context
import zmq
import asyncio

from pycoin.block import Block
from pycoin.merkle import merkle

from spruned.daemon.tasks.headers_reactor import HeadersReactor
from spruned.daemon.zeromq import build_zmq, BitcoindZMQTopics


class TestZeroMQ(TestCase):
    def setUp(self):
        self.context = Mock()
        self.mempool_observer = Mock()
        self.headers_reactor = create_autospec(HeadersReactor)
        self.mempool_status = True
        self.vo_service = Mock()
        self._callbacks = {}
        self._setup_reactor()
        self._loop = asyncio.get_event_loop()
        self._data_from_topics = {}
        signal.signal(signal.SIGINT, signal.SIG_DFL)

    def _setup_reactor(self):
        def _save(topic, data):
            self._callbacks[topic] = data
        self.headers_reactor.add_on_new_header_callback = lambda x: _save('new_header', x)
        self.mempool_observer.on_new_block_callback = lambda x: _save('new_block', x)
        self.mempool_observer.add_on_transaction_hash_callback = lambda x: _save('new_tx_hash', x)
        self.mempool_observer.add_on_transaction_callback = lambda x: _save('new_tx', x)

    def _build(self):
        self.ctx, self.obs = build_zmq(
            self.context,
            self.mempool_observer,
            self.headers_reactor,
            self.mempool_status,
            self.vo_service
        )

    def setup_zmq_urls(self):
        self.context.zmqpubrawtx = 'tcp://127.0.0.1:{}'.format(random.randint(10000, 64000))
        self.context.zmqpubhashtx = 'tcp://127.0.0.1:{}'.format(random.randint(10000, 64000))
        self.context.zmqpubrawblock = 'tcp://127.0.0.1:{}'.format(random.randint(10000, 64000))
        self.context.zmqpubhashblock = 'tcp://127.0.0.1:{}'.format(random.randint(10000, 64000))

    def _get_block_with_tx(self):
        from pycoin.tx.Tx import Tx
        tx = Tx.from_hex(
            '01000000000101112a649fd72656cf572259cb7cb61bd31ccdbdf0944070e73401565affbe629d0100000000ffffffff02608'
            'de2110000000017a914d52b516c1a094462959ed6facebb94429d2cebf487d3135b0b00000000220020701a8d401c84fb13e6'
            'baf169d59684e17abd9fa216c8cc5b9fc63d622ff8c58d0400473044022006b149e0cf031f57fd443bd1210b381e9b1b15094'
            '57ba1f49e48b803696f56e802203d66bd974ad3ac5b7591cc84e706b78d139c61e2bf1995a89c4dc0758984a2b70148304502'
            '2100fe7275d601080e1870517774a3ad6accaa7f8ad144addec3251e98685d4fefad02207792c2b0ed6ab42ed2ba6d12e6bd3'
            '4db8c6f4ac6f15e604f70ea85a735c450b1016952210375e00eb72e29da82b89367947f29ef34afb75e8654f6ea368e0acdfd'
            '92976b7c2103a1b26313f430c4b15bb1fdce663207659d8cac749a0e53d70eff01874496feff2103c96d495bfdd5ba4145e3e'
            '046fee45e84a8a48ad05bd8dbb395c011a32cf9f88053ae00000000'
        )
        block = Block(1, b'0' * 32, merkle_root=merkle([tx.hash()]), timestamp=123456789, difficulty=3000000,
                      nonce=1 * 137)
        block.txs.append(tx)
        return block

    async def _subscribe_topic(self, topic, url, max_msgs):
            with Context() as ctx:
                socket = ctx.socket(zmq.SUB)
                socket.connect(url)
                socket.subscribe(topic)
                if not self._data_from_topics.get(topic):
                    self._data_from_topics[topic] = []
                x = 0
                while x < max_msgs:
                    x += 1
                    print('waiting')
                    msg = await socket.recv_multipart()
                    print('done')
                    self._data_from_topics[topic].append(msg)
                socket.close()
                print('socket closed')

    def test_zmq(self):
        block = self._get_block_with_tx()
        self.setup_zmq_urls()
        self._build()
        _tasks = [
            self._subscribe_topic(BitcoindZMQTopics.TX.value, self.context.zmqpubrawtx, 1),
            self._subscribe_topic(BitcoindZMQTopics.TXHASH.value, self.context.zmqpubhashtx, 2),
            self._subscribe_topic(BitcoindZMQTopics.BLOCK.value, self.context.zmqpubrawblock, 1),
            self._subscribe_topic(BitcoindZMQTopics.BLOCKHASH.value, self.context.zmqpubhashblock, 1),
            self._test_zmq(block)
        ]
        self._loop.run_until_complete(asyncio.gather(*_tasks))

    async def _test_zmq(self, block):
        await asyncio.sleep(3)
        await self._callbacks['new_header']({'block_hash': block.id()})
        await self._callbacks['new_block'](block)
        await self._callbacks['new_tx_hash'](b'f'*32)
        await asyncio.sleep(3)

        txhash_data = self._data_from_topics[BitcoindZMQTopics.TXHASH.value]
        self.assertEqual(txhash_data[0][0], BitcoindZMQTopics.TXHASH.value)
        self.assertEqual(txhash_data[0][1], block.txs[0].w_hash())
        self.assertEqual(txhash_data[1][0], BitcoindZMQTopics.TXHASH.value)
        self.assertEqual(txhash_data[1][1], b'f'*32)

        rawblock_data = self._data_from_topics[BitcoindZMQTopics.BLOCK.value]
        self.assertEqual(rawblock_data[0][0], BitcoindZMQTopics.BLOCK.value)
        self.assertEqual(rawblock_data[0][1], block.as_bin())

        tx_data = self._data_from_topics[BitcoindZMQTopics.TX.value]
        self.assertEqual(tx_data[0][0], BitcoindZMQTopics.TX.value)
        self.assertEqual(tx_data[0][1], block.txs[0].as_bin())

        block_hash_data = self._data_from_topics[BitcoindZMQTopics.BLOCKHASH.value]
        self.assertEqual(block_hash_data[0][0], BitcoindZMQTopics.BLOCKHASH.value)
        self.assertEqual(block_hash_data[0][1], binascii.unhexlify(str(block.hash())))

        self.obs.close_zeromq()
