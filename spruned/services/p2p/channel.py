import asyncio
from asyncio import IncompleteReadError
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
        response = await self._msg('getdata', response_message, {'items': (request_message, )})
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
            future = self._responses_listeners.pop(name, None)
            self._lock.locked() and self._lock.release()
            future and future.cancel()

    def set_event_callbacks(self, name, callback_f):
        self._events_callbacks[name] = callback_f

    async def get_event(self):
        try:
            return await self.connection.peer.next_message()
        except IncompleteReadError as e:
            Logger.p2p.error(str(e))

    async def _run(self):
        while True:
            event = await self.get_event()
            if event is None:
                break
            name, data = event
            self._fire_callback(name, data)
            await asyncio.sleep(0.001)

    async def run(self):
        try:
            await self._run()
        finally:
            self.loop.create_task(self.connection.disconnect())

    def _evaluate_merkleblock_on_pending_responses(self, name, data):
        header = data['header']
        resp_name = f'{name}|{bytes.fromhex(str(header.hash()))[::-1]}'
        if resp_name in self._responses_listeners:
            self._responses_listeners[resp_name].set_result(data)
            self._responses_listeners.pop(resp_name, None)
            return
        return {name: data}

    @staticmethod
    def _serialize_block_response(data: BytesIO):
        header: bytes = data.read(80)
        block_hash = blockheader_to_blockhash(header)
        response = {
            'block_hash': block_hash,
            'header_bytes': header,
            'data': data
        }
        return response

    def _evaluate_block_on_pending_responses(self, name, data: typing.Dict):
        resp_name = f'{name}|{data["block_hash"][::-1]}'
        if resp_name in self._responses_listeners:
            self._responses_listeners[resp_name].set_result(data)
            self._responses_listeners.pop(resp_name, None)
            return
        return data

    def _evaluate_headers_on_pending_responses(self, name: str, data: typing.Dict):
        h = data['headers'][0]
        resp_name = f'{name}|{str(h[0].previous_block_hash)}'
        if resp_name in self._responses_listeners:
            self._responses_listeners[resp_name].set_result(data)
            self._responses_listeners.pop(resp_name, None)
            return
        return data

    def _fire_callback(self, name: str, data: typing.Dict):
        # this is awful, will go away with built-ins refactoring
        processed = None
        if name == 'block':
            processed = self._serialize_block_response(data['block'])

        if any(map(lambda f: f.startswith(f'{name}|'), self._responses_listeners)):
            if name == 'block':
                processed = self._evaluate_block_on_pending_responses(name, processed)
            elif name == 'headers':
                data = self._evaluate_headers_on_pending_responses(name, data)

        if not data:  # event handled by the custom handlers
            return

        elif name in self._responses_listeners:
            self._responses_listeners[name].set_result(processed or data)
            self._responses_listeners.pop(name, None)
        elif name in self._events_callbacks:
            self._events_callbacks[name](self, name, processed or data)
        else:
            Logger.p2p.error('UNKNOWN MESSAGE - %s - %s', name, data)

