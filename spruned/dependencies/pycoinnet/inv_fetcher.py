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
import weakref

from spruned.dependencies.pycoinnet.pycoin.InvItem import InvItem, ITEM_TYPE_TX, ITEM_TYPE_BLOCK, \
    ITEM_TYPE_MERKLEBLOCK, ITEM_TYPE_SEGWIT_BLOCK, ITEM_TYPE_SEGWIT_TX


class InvFetcher:
    """
    This class handles fetching transaction, block, or merkleblock objects
    advertised by an "inv" message. It automatically coalesces repeated requests
    for the same object.

    Fetching a merkleblock also fetches the transactions that follow, and
    includes futures to them in the message as the "tx" key.
    """
    def __init__(self, peer, batch_size=50000):
        """
        peer: a Peer object
        batch_size: maximum number of objects to include in a single "getdata" message
        """
        self._peer = peer
        self._request_q = asyncio.Queue()
        self._futures = dict() #weakref.WeakValueDictionary()
        self._batch_size = batch_size
        self._send_getdata_lock = asyncio.Lock()
        self._is_closed = False

    def _future_for_inv_item(self, inv_item):
        """
        Return the future associated with inv_item, creating
        it if necessary.
        """
        future = self._futures.get(inv_item)
        if not future:
            future = asyncio.Future()
            self._futures[inv_item] = future
        return future

    def fetch(self, inv_item, timeout=None):
        """
        Return the fetched object or None if the remote says it doesn't have it, or
        times out by exceeding `timeout` seconds.
        """
        future = self._futures.get(inv_item)
        if not future:
            future = self._future_for_inv_item(inv_item)
            if self._request_q.qsize() == 0:
                asyncio.get_event_loop().create_task(self._send_getdata())
            self._request_q.put_nowait(inv_item)
        if self._is_closed:
            future.set_exception(EOFError())
        if timeout is None:
            return future
        try:
            return asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def pending_response_count(self):
        """
        Return the number of items that have been requested to the remote
        that have not yet been answered.
        """
        return sum(1 for f in self._futures.values() if not f.done())

    def pending_request_count(self):
        """
        Return the number of items that are waiting to be requested to the remote.
        """
        return self._request_q.qsize()

    @asyncio.coroutine
    def _send_getdata(self):
        """
        This is the task that sends a message to the peer requesting objects
        that have been requested. It coalesces requests for multiple objects
        into one message.
        """
        with (yield from self._send_getdata_lock):
            while self._request_q.qsize() > 0:
                so_far = []
                while self._request_q.qsize() > 0:
                    inv_item = yield from self._request_q.get()
                    so_far.append(inv_item)
                    if len(so_far) >= self._batch_size:
                        break
                self._peer.send_msg("getdata", items=so_far)

    ITEM_LOOKUP = dict(
        tx="tx",
        block="block",
        merkleblock="header",
        segwit_tx="segwit_tx",
        segwit_block="segwit_block"
    )
    TYPE_DB = dict(
        tx=ITEM_TYPE_TX,
        block=ITEM_TYPE_BLOCK,
        merkleblock=ITEM_TYPE_MERKLEBLOCK,
        segwit_tx=ITEM_TYPE_SEGWIT_TX,
        segwit_block=ITEM_TYPE_SEGWIT_BLOCK
    )

    @asyncio.coroutine
    def handle_msg(self, msg_name, msg_data):
        """
        This method must be invoked for each message that comes from the peer
        (or at least, those of type tx, block, merkleblock and notfound).
        It resolves the appropriate futures and handles the messy merkleblock
        message (where a the given list of transactions are automatically sent
        after the merkleblock message is sent).

        The "merkleblock" item is augmented with .tx_futures that can be
        waited on.
        """
        if msg_name is None:
            self._is_closed = True
            for f in self._futures.values():
                if not f.done():
                    f.set_exception(EOFError())
        if msg_name in self.ITEM_LOOKUP:
            item = msg_data[self.ITEM_LOOKUP[msg_name]]
            the_hash = item.hash()
            the_type = self.TYPE_DB[msg_name]
            inv_item = InvItem(the_type, the_hash)
            future = self._futures.get(inv_item)
            if future is None:
                return
            if msg_name == "merkleblock":
                # we now expect a bunch of tx messages
                tx_inv_items = [InvItem(ITEM_TYPE_TX, h)
                                for h in msg_data["tx_hashes"]]
                # create futures for items
                # we don't need to add them to the request queue since
                # they're supposed to be sent next anyway
                item.tx_futures = [self._future_for_inv_item(inv_item)
                                   for inv_item in tx_inv_items]
                # we need to keep the futures around so they're not automatically
                # garbage collected, as they're kept in a WeakValueDictionary
                # so they're jammed into the item (which is a merkleblock).
                # Once the item is gone, we don't care about the futures anyway.
            if not future.done():
                future.set_result(item)
        if msg_name == "notfound":
            for inv_item in msg_data["items"]:
                the_hash = inv_item.data
                future = self._futures.get(inv_item)
                if future is not None:
                    # we don't need to delete the future since it should
                    # be garbage collected, but hey, why not
                    del self._futures[inv_item]
                    future.set_result(None)
