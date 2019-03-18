import async_timeout
import threading, queue
from pycoin.block import Block

from spruned.dependencies.pycoinnet.dnsbootstrap import dns_bootstrap_host_port_q
from spruned.dependencies.pycoinnet.networks import TESTNET
import asyncio
from spruned.application.logging_factory import Logger


async def dns_bootstrap_servers(network=TESTNET, howmany=50):  # pragma: no cover
    host_q = dns_bootstrap_host_port_q(network)
    ad = []
    while 1:
        item = host_q.get()
        try:
            async with async_timeout.timeout(1):
                peer = await item
        except asyncio.TimeoutError:
            try:
                item.close()
            except asyncio.CancelledError:
                Logger.p2p.debug('Cancelled')
            break
        ad.append(peer)
    return ad


class AsyncBlockFactory:
    def __init__(self, min_size=100000):
        self.min_size = min_size

    @staticmethod
    def getblock(data, q):
        q.put(Block.from_bin(data))

    async def get(self, block_bytes: bytes):
        if not self.min_size or len(block_bytes) <= self.min_size:
            return Block.from_bin(block_bytes)
        else:
            q = queue.Queue()
            thread = threading.Thread(target=self.getblock, args=(block_bytes, q))
            thread.start()
            try:
                while 1:
                    try:
                        data = q.get(block=False)
                        return data
                    except:
                        pass
                    await asyncio.sleep(0.1)
            finally:
                del thread


def get_block_factory():
    return AsyncBlockFactory()
