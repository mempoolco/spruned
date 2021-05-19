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
from io import BytesIO

import typing
from pycoin.block import Block

from spruned.application.tools import blockheader_to_blockhash
from spruned.dependencies.pycoinnet import logger
from spruned.dependencies.pycoinnet.pycoin.InvItem import ITEM_TYPE_SEGWIT_BLOCK, InvItem, ITEM_TYPE_BLOCK


class PeerEvent:
    def __init__(self, peer):
        self._peer = peer
        self._request_callbacks = dict()
        self._response_futures = dict()
        self._task = asyncio.ensure_future(self.process_events())
        self.request_response_lock = asyncio.Lock()

    def send_msg(self, *args, **kwargs):
        self._peer.send_msg(*args, **kwargs)

    async def getblock(self, request_message: InvItem):
        response_message = {
            ITEM_TYPE_SEGWIT_BLOCK: 'block',
            ITEM_TYPE_BLOCK: 'block'
        }[request_message.item_type]
        response_message = f'{response_message}|{request_message.data}'
        response = await self.getdata(response_message, request_message)
        return response

    async def getdata(self, response_message: str, *request_messages: InvItem):
        try:
            await self.request_response_lock.acquire()
            if response_message in self._request_callbacks:
                await self._request_callbacks[response_message]
            self._response_futures[response_message] = asyncio.Future()
            self.send_msg('getdata', items=request_messages)
            return await self._response_futures[response_message]
        finally:
            self.request_response_lock.release()

    def set_request_callback(self, name, callback_f):
        self._request_callbacks[name] = callback_f

    async def process_events(self):
        while True:
            try:
                event = await self._peer.next_message()
                if event is None:
                    break
                name, data = event
                self._fire_callback(name, data)
            except:
                logger.exception('Error process_events')
                raise

    def _evaluate_block_on_pending_responses(self, name, data):
        data_bytes: bytes = data[name].getvalue()
        header = data_bytes[:80]
        block_hash = blockheader_to_blockhash(header)
        resp_name = f'{name}|{block_hash[::-1]}'
        if resp_name in self._response_futures:
            self._response_futures[resp_name].set_result(data_bytes)
            self._response_futures.pop(resp_name, None)
            return
        return {'block': BytesIO(data_bytes)}

    def _fire_callback(self, name: str, data: typing.Dict):
        if name == 'block' and any(map(lambda f: f.startswith('block|'), self._response_futures)):
            data = self._evaluate_block_on_pending_responses(name, data)
        if not data:
            return
        elif name in self._response_futures:
            self._response_futures[name].set_result(data)
            self._response_futures.pop(name, None)
        elif name in self._request_callbacks:
            self._request_callbacks[name](self, name, data)
        else:
            logger.debug('Unhandled exception')

    def __repr__(self):
        return "<Peer %s>" % str(self._peer.peername())
