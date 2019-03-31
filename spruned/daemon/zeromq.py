import signal
import threading
from enum import Enum

import asyncio
import zmq
import zmq.asyncio
from pycoin.block import Block
from pycoin.tx.Tx import Tx
from spruned.daemon import exceptions

from spruned.application.logging_factory import Logger
from spruned.daemon.tasks.headers_reactor import HeadersReactor
import binascii

_SOCKETS = threading.local()


class ZeroMQPublisher:
    def __init__(self, endpoint: str, topic: bytes, context: zmq.asyncio.Context):
        self._endpoint = endpoint
        self._topic = topic
        self.context = context
        self.setup_socket()

    async def on_event(self, data: bytes, retries=0):
        try:
            await self.socket.send_multipart([self._topic, data])
        except Exception as e:
            if retries:
                raise
            Logger.zmq.warning('Error: %s' % e)
            await asyncio.sleep(0.5)
            try:
                self.socket.close()
            except:
                pass
            setattr(_SOCKETS, self._endpoint, None)
            await self.on_event(data, retries=retries+1)

    def setup_socket(self):
        if not getattr(_SOCKETS, self._endpoint, None):
            s = self.context.socket(zmq.PUB)
            setattr(_SOCKETS, self._endpoint, s)
            s.bind(self._endpoint)

    @property
    def socket(self):
        not getattr(_SOCKETS, self._endpoint, None) and self.setup_socket()
        return getattr(_SOCKETS, self._endpoint)


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
        self.context = None

        self.publishers = [
            self.transaction_publisher,
            self.transaction_hash_publisher,
            self.block_publisher,
            self.blockhash_publisher
        ]

        self.sockets = [p.socket for p in self.publishers if p]

    async def on_transaction(self, tx: Tx):
        self.transaction_publisher and await self.transaction_publisher.on_event(tx.as_bin())

    async def on_transaction_hash(self, txhash: bytes):
        self.transaction_hash_publisher and await self.transaction_hash_publisher.on_event(txhash)

    async def on_block_hash(self, data):
        block_hash = binascii.unhexlify(data['block_hash'].encode())
        self.blockhash_publisher and await self.blockhash_publisher.on_event(block_hash)

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

    def close_zeromq(self):
        for socket in self.sockets:
            try:
                socket.close()
            except:
                pass
        self.context.destroy()


def build_zmq(ctx, mempool_observer, headers_reactor: HeadersReactor, mempool_status, vo_service):
    zmq_ctx = zmq.asyncio.Context.instance()
    zeromq_observer = ZeroMQObserver()
    zeromq_observer.context = zmq_ctx
    zeromq_observer.service = vo_service

    async def processblock(data, retries=0):
        blockhash = data['block_hash']
        try:
            block = await vo_service.get_block_object(blockhash)
        except exceptions.NoPeersException:
            if retries < 10:
                await asyncio.sleep(10)
                return await processblock(data, retries=retries + 1)
            raise
        await zeromq_observer.on_raw_block(block)

    rawblock_on = False

    def _setup_rawblock():
        nonlocal rawblock_on
        if rawblock_on:
            return
        rawblock_on = True
        zeromq_observer.block_publisher = ctx.zmqpubrawblock and \
                         ZeroMQPublisher(ctx.zmqpubrawblock, BitcoindZMQTopics.BLOCK.value, zmq_ctx)
        if mempool_status:
            mempool_observer.add_on_new_block_callback(zeromq_observer.on_raw_block)
        else:
            headers_reactor.add_on_new_header_callback(processblock)

    if ctx.zmqpubrawtx:
        Logger.zmq.info('Setting up ZMQ, zmqpubrawtx on %s', ctx.zmqpubrawtx)
        zmqpubrawtx = ZeroMQPublisher(ctx.zmqpubrawtx, BitcoindZMQTopics.TX.value, zmq_ctx)
        zeromq_observer.transaction_publisher = zmqpubrawtx
        mempool_status and mempool_observer.add_on_transaction_callback(zeromq_observer.on_transaction)
        not rawblock_on and _setup_rawblock()

    if ctx.zmqpubhashtx:
        Logger.zmq.info('Setting up ZMQ, zmqpubhashtx on %s', ctx.zmqpubhashtx)
        zmqpubhashtx = ZeroMQPublisher(ctx.zmqpubhashtx, BitcoindZMQTopics.TXHASH.value, zmq_ctx)
        zeromq_observer.transaction_hash_publisher = zmqpubhashtx
        mempool_status and mempool_observer.add_on_transaction_hash_callback(zeromq_observer.on_transaction_hash)
        not rawblock_on and _setup_rawblock()

    if ctx.zmqpubrawblock:
        Logger.zmq.info('Setting up ZMQ, zmqpubrawblock on %s', ctx.zmqpubrawblock)
        not rawblock_on and _setup_rawblock()

    if ctx.zmqpubhashblock:
        Logger.zmq.info('Setting up ZMQ, zmqpubhashblock on %s', ctx.zmqpubhashblock)
        zmqpubhashblock = ZeroMQPublisher(ctx.zmqpubhashblock, BitcoindZMQTopics.BLOCKHASH.value, zmq_ctx)
        zeromq_observer.blockhash_publisher = zmqpubhashblock
        headers_reactor.add_on_new_header_callback(zeromq_observer.on_block_hash)

    def close_zeromq_and_exit(*a, **kw):
        import sys
        zeromq_observer.close_zeromq()
        sys.exit()

    signal.signal(signal.SIGINT, close_zeromq_and_exit)
    return zmq_ctx, zeromq_observer
