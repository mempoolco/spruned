import asyncio
from io import BytesIO

import typing

import async_timeout

from spruned.application.logging_factory import Logger
from spruned.application.tools import blockheader_to_blockhash
from spruned.dependencies.pycoinnet.peer import ProtocolError
from spruned.dependencies.pycoinnet.pycoin.inv_item import ITEM_TYPE_SEGWIT_BLOCK, InvItem, ITEM_TYPE_BLOCK, \
    ITEM_TYPE_MERKLEBLOCK


class P2PChannel:
    def __init__(self, connection, loop=asyncio.get_event_loop()):
        self.loop = loop
        self.connection = connection
        self._events_callbacks = dict()
        self._responses_listeners = dict()
        self._lock = asyncio.Lock()
        self._task = self.loop.create_task(self.run())

    def send_msg(self, *args, **kwargs):
        self.connection.peer.send_msg(*args, **kwargs)

    async def get_inv_item(self, request_message: InvItem):
        response_message = {
            ITEM_TYPE_SEGWIT_BLOCK: 'block',
            ITEM_TYPE_BLOCK: 'block',
            ITEM_TYPE_MERKLEBLOCK: 'merkleblock',
        }[request_message.item_type]
        response_message = f'{response_message}|{request_message.data}'
        response = await self._msg('getdata', response_message, {'items': request_message})
        return response

    async def get(self, message: str, lock_key: str, payload: typing.Dict, timeout=999):
        future_msg = {
            'getheaders': 'headers'
        }[message]
        name = f'{future_msg}|{lock_key}'
        response = await self._msg(message, name, payload, timeout=timeout)
        return response

    async def _msg(self, message: str, name: str, payload: typing.Dict, timeout=999):
        await self._lock.acquire()
        try:
            if name not in self._responses_listeners:
                self._responses_listeners[name] = asyncio.Future()
                self.send_msg(message, **payload)
            async with async_timeout.timeout(timeout):
                return await self._responses_listeners[name]
        finally:
            self._responses_listeners.pop(name, None)
            self._lock.locked() and self._lock.release()

    def set_event_callbacks(self, name, callback_f):
        self._events_callbacks[name] = callback_f

    async def run(self):
        try:
            while True:
                event = await self.connection.peer.next_message()
                if event is None:
                    break
                name, data = event
                self._fire_callback(name, data)
            await asyncio.sleep(0.001)
        except ProtocolError:
            self.loop.create_task(self.connection.disconnect())
            return

    def _evaluate_merkleblock_on_pending_responses(self, name, data):
        header = data['header']
        resp_name = f'{name}|{bytes.fromhex(str(header.hash()))[::-1]}'
        if resp_name in self._responses_listeners:
            self._responses_listeners[resp_name].set_result(data)
            self._responses_listeners.pop(resp_name, None)
            return
        return {name: data}

    def _evaluate_block_on_pending_responses(self, name, data):
        data_bytes: bytes = data[name].getvalue()
        header = data_bytes[:80]
        block_hash = blockheader_to_blockhash(header)
        resp_name = f'{name}|{block_hash[::-1]}'
        if resp_name in self._responses_listeners:
            self._responses_listeners[resp_name].set_result(data_bytes)
            self._responses_listeners.pop(resp_name, None)
            return
        return {name: BytesIO(data_bytes)}

    def _evaluate_headers_on_pending_responses(self, name: str, data: typing.Dict):
        h = data['headers'][0]
        resp_name = f'{name}|{str(h[0].previous_block_hash)}'
        if resp_name in self._responses_listeners:
            self._responses_listeners[resp_name].set_result(data)
            self._responses_listeners.pop(resp_name, None)
            return
        return data

    def _fire_callback(self, name: str, data: typing.Dict):
        if any(map(lambda f: f.startswith(f'{name}|'), self._responses_listeners)):
            if name == 'block':
                data = self._evaluate_block_on_pending_responses(name, data)
            elif name == 'merkleblock':
                data = self._evaluate_merkleblock_on_pending_responses(name, data)
            elif name == 'headers':
                data = self._evaluate_headers_on_pending_responses(name, data)
        if not data:  # event handled by the custom handlers
            return
        elif name in self._responses_listeners:
            self._responses_listeners[name].set_result(data)
            self._responses_listeners.pop(name, None)
        elif name in self._events_callbacks:
            self._events_callbacks[name](self, name, data)
        else:
            Logger.p2p.error('UNKOWN MESSAGE - %s - %s', name, data)

