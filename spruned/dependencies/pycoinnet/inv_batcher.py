#
# https://github.com/richardkiss/pycoinnet/
#
# The MIT License (MIT)
#
# Copyright (c) 2014 Richard Kiss
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

import asyncio

from spruned.application.tools import blockheader_to_blockhash
from spruned.dependencies.pycoinnet.pycoin.InvItem import \
    InvItem, ITEM_TYPE_BLOCK, ITEM_TYPE_MERKLEBLOCK
from spruned.dependencies.pycoinnet.MappingQueue import MappingQueue
from spruned.dependencies.pycoinnet import logger


class InvBatcher:
    def __init__(self, target_batch_time=10, max_batch_size=500, inv_item_future_q_maxsize=1000):

        self._is_closing = False
        self._inv_item_future_queue = asyncio.PriorityQueue(maxsize=inv_item_future_q_maxsize)

        async def batch_getdata_fetches(peer_batch_tuple, q):
            peer, desired_batch_size = peer_batch_tuple
            batch = []
            skipped = []
            logger.info("peer %s trying to build batch up to size %d", peer, desired_batch_size)
            while len(batch) == 0 or (
                    len(batch) < desired_batch_size and not self._inv_item_future_queue.empty()):
                item = await self._inv_item_future_queue.get()
                (priority, inv_item, f, peers_tried) = item
                if f.done():
                    continue
                if peer in peers_tried:
                    skipped.append(item)
                else:
                    batch.append(item)
            if len(batch) > 0:
                await q.put((peer, batch, desired_batch_size))
            for item in skipped:
                if not item[2].done:
                    await self._inv_item_future_queue.put(item)

        async def fetch_batch(peer_batch, q):
            loop = asyncio.get_event_loop()
            peer, batch, prior_max = peer_batch
            inv_items = [inv_item for (priority, inv_item, f, peers_tried) in batch]
            peer.send_msg("getdata", items=inv_items)
            start_time = loop.time()
            futures = [f for (priority, bh, f, peers_tried) in batch]
            await asyncio.wait(futures, timeout=target_batch_time)
            end_time = loop.time()
            batch_time = end_time - start_time
            logger.info("completed batch size of %d with time %f", len(inv_items), batch_time)
            completed_count = sum([1 for f in futures if f.done()])
            item_per_unit_time = completed_count / batch_time
            new_batch_size = min(prior_max * 4, int(target_batch_time * item_per_unit_time + 0.5))
            new_batch_size = min(max(1, new_batch_size), max_batch_size)
            logger.info("new batch size for %s is %d", peer, new_batch_size)
            for (priority, inv_item, f, peers_tried) in batch:
                if not f.done():
                    peers_tried.add(peer)
                    await self._inv_item_future_queue.put((priority, inv_item, f, peers_tried))
            await self._peer_batch_queue.put((peer, new_batch_size))

        self._peer_batch_queue = MappingQueue(
            dict(callback_f=batch_getdata_fetches),
            dict(callback_f=fetch_batch, input_q_maxsize=2),
        )

        self._inv_item_hash_to_future = dict()

    async def add_peer(self, peer, initial_batch_size=1):
        peer.set_request_callback("block", self.handle_block_event)
        peer.set_request_callback("merkleblock", self.handle_block_event)
        await self._peer_batch_queue.put((peer, initial_batch_size))
        await self._peer_batch_queue.put((peer, initial_batch_size))

    async def inv_item_to_future(self, inv_item: InvItem, priority=0):
        f = self._inv_item_hash_to_future.get(inv_item)
        if not f:
            f = asyncio.Future()
            self._inv_item_hash_to_future[str(inv_item)] = f

            def remove_later(f):

                def remove():
                    if str(inv_item) in self._inv_item_hash_to_future:
                        del self._inv_item_hash_to_future[str(inv_item)]

                asyncio.get_event_loop().call_later(5, remove)

            f.add_done_callback(remove_later)
            item = (priority, inv_item, f, set())
            await self._inv_item_future_queue.put(item)
        return f

    def handle_block_event(self, peer, name, data):
        block_fp = data["block" if name == "block" else "header"]
        block_bytes = block_fp.read()
        block_hash = blockheader_to_blockhash(block_bytes[:80])

        if name == "block":
            inv_item = InvItem(ITEM_TYPE_BLOCK, block_hash[::-1])
        elif name == "header":
            inv_item = InvItem(ITEM_TYPE_MERKLEBLOCK, block_hash[::-1])
        else:
            raise ValueError(peer, name, data)
        if str(inv_item) in self._inv_item_hash_to_future:
            f = self._inv_item_hash_to_future[str(inv_item)]
            if not f.done():
                f.set_result(block_bytes)
        else:
            logger.warning("missing future for block %s", block_hash)

    def stop(self):
        self._peer_batch_queue.stop()

