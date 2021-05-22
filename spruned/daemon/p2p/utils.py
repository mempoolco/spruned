import itertools
import queue
import threading
from pycoin.block import Block

from spruned.dependencies.pycoinnet.networks import TESTNET
import asyncio


async def dns_bootstrap_servers(network=TESTNET):  # pragma: no cover
    hosts = set()
    fn = asyncio.get_event_loop().getaddrinfo
    done, pending = await asyncio.wait(
        map(
            lambda x: fn(x, network.default_port),
            network.dns_bootstrap,
        ),
        timeout=2
    )
    for f in itertools.chain(done, pending):
        hosts.update(
            set(
                map(
                    lambda r: (r[4][0], r[4][1]),
                    f.result()
                )
            )
        ) if f.done() else f.cancel()
    return hosts


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
            thread.join()
            data = q.get(block=False)
            return data


def get_block_factory():
    return AsyncBlockFactory()
