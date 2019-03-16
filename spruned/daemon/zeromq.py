from enum import Enum

import asyncio
import zmq
import zmq.asyncio
from pycoin.block import Block
from pycoin.tx.Tx import Tx
from spruned.daemon import exceptions

from spruned.application.logging_factory import Logger
from spruned.daemon.tasks.headers_reactor import HeadersReactor

zmq_ctx = zmq.asyncio.Context()
_SOCKETS = {}


class ZeroMQPublisher:
    def __init__(self, endpoint: str, topic: bytes):
        self._endpoint = endpoint
        self._topic = topic
        self.setup_socket()

    async def on_event(self, data: bytes, _r=0):
        try:
            await self.socket.send(b'%s %s' % (self._topic, data))
            Logger.zmq.debug('Published on topic %s' % self._topic.decode())
        except Exception as e:
            if _r:
                raise
            Logger.zmq.warning('Error: %s' % e)
            del _SOCKETS[self._endpoint]
            await asyncio.sleep(0.5)
            _SOCKETS[self._endpoint] = None
            await self.on_event(data, _r=_r+1)

    def setup_socket(self):
        if not _SOCKETS.get(self._endpoint):
            _SOCKETS[self._endpoint] = zmq_ctx.socket(zmq.PUB)
            _SOCKETS[self._endpoint].bind(self._endpoint)

    @property
    def socket(self):
        not _SOCKETS[self._endpoint] and self.setup_socket()
        return _SOCKETS[self._endpoint]


class BitcoindZMQTopics(Enum):
    TX = b'rawtx'
    TXHASH = b'hashtx'
    BLOCK = b'rawblock'
    BLOCKHASH = b'hashblock'


class ZeroMQObserver:
    def __init__(self):
        self.transaction_publisher = None
        self.transaction_hash_publisher = None
        self.block_publisher = None
        self.blockhash_publisher = None
        self.service = None

    async def on_transaction(self, tx: Tx):
        self.transaction_publisher and await self.transaction_publisher.on_event(tx.as_bin())

    async def on_transaction_hash(self, txhash: bytes):
        self.transaction_hash_publisher and await self.transaction_hash_publisher.on_event(txhash)

    async def on_block_hash(self, data):
        self.blockhash_publisher and await self.blockhash_publisher.on_event(data['header_bytes'])

    async def on_raw_block(self, block: Block):
        _futures = []
        if not self.transaction_publisher and not self.transaction_hash_publisher and not self.block_publisher:
            return
        self.transaction_publisher and _futures.extend([self.on_transaction(tx) for tx in block.txs])
        self.transaction_hash_publisher and _futures.extend(
            [self.on_transaction_hash(tx.w_hash()) for tx in block.txs]
        )
        self.block_publisher and _futures.append(self.block_publisher.on_event(block.as_bin()))
        _futures and await asyncio.gather(*_futures)


def build_zmq(ctx, mempool_observer, headers_reactor: HeadersReactor, mempool_status, vo_service):
    zeromq_observer = ZeroMQObserver()
    zeromq_observer.service = vo_service

    async def processblock(data, _r=0):
        blockhash = data['block_hash']
        try:
            block = await vo_service.get_block_object(blockhash)
        except exceptions.NoPeersException:
            if _r < 10:
                await asyncio.sleep(10)
                return await processblock(data, _r=_r + 1)
            raise
        await zeromq_observer.on_raw_block(block)

    def _setup_rawblock():
        zmqpubrawblock = ZeroMQPublisher(ctx.zmqpubrawblock, BitcoindZMQTopics.BLOCK.value)
        zeromq_observer.block_publisher = zmqpubrawblock
        if mempool_status:
            mempool_observer.on_new_block_callback(zeromq_observer.on_raw_block)
        else:
            headers_reactor.add_on_new_header_callback(processblock)

    if ctx.zmqpubrawtx:
        Logger.zmq.info('Setting up ZMQ, zmqpubrawtx on %s', ctx.zmqpubrawtx)
        zmqpubrawtx = ZeroMQPublisher(ctx.zmqpubrawtx, BitcoindZMQTopics.TX.value)
        zeromq_observer.transaction_publisher = zmqpubrawtx
        mempool_status and mempool_observer.add_on_transaction_callback(zeromq_observer.on_transaction)
        not ctx.zmqpubrawblock and _setup_rawblock()

    if ctx.zmqpubhashtx:
        Logger.zmq.info('Setting up ZMQ, zmqpubhashtx on %s', ctx.zmqpubhashtx)
        zmqpubhashtx = ZeroMQPublisher(ctx.zmqpubhashtx, BitcoindZMQTopics.TXHASH.value)
        zeromq_observer.transaction_hash_publisher = zmqpubhashtx
        mempool_status and mempool_observer.add_on_transaction_hash_callback(zeromq_observer.on_transaction_hash)
        not ctx.zmqpubrawblock and _setup_rawblock()

    if ctx.zmqpubrawblock:
        Logger.zmq.info('Setting up ZMQ, zmqpubrawblock on %s', ctx.zmqpubrawblock)
        _setup_rawblock()

    if ctx.zmqpubhashblock:
        Logger.zmq.info('Setting up ZMQ, zmqpubhashblock on %s', ctx.zmqpubhashblock)
        zmqpubhashblock = ZeroMQPublisher(ctx.zmqpubhashblock, BitcoindZMQTopics.BLOCKHASH.value)
        zeromq_observer.blockhash_publisher = zmqpubhashblock
        headers_reactor.add_on_new_header_callback(zeromq_observer.on_block_hash)
