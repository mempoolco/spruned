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
from spruned.dependencies.pycoinnet import logger


class PeerEvent:
    def __init__(self, peer):
        self._peer = peer
        self._request_callbacks = dict()
        self._response_futures = dict()
        self._task = asyncio.ensure_future(self.process_events())

    def send_msg(self, *args, **kwargs):
        self._peer.send_msg(*args, **kwargs)

    async def request_response(self, request_message, response_message, **kwargs):
        if response_message in self._request_callbacks:
            await self._request_callbacks[response_message]
        self._response_futures[response_message] = asyncio.Future()
        self.send_msg(request_message, **kwargs)
        return await self._response_futures[response_message]

    def set_request_callback(self, name, callback_f):
        self._request_callbacks[name] = callback_f

    async def process_events(self):
        while True:
            event = await self._peer.next_message()
            if event is None:
                break
            name, data = event
            if name in self._request_callbacks:
                self._request_callbacks[name](self, name, data)
            elif name in self._response_futures:
                self._response_futures[name].set_result(data)
                del self._response_futures[name]
            else:
                logger.error("unhandled event %s %s", event[0], event[1])

    def __repr__(self):
        return "<Peer %s>" % str(self._peer.peername())
