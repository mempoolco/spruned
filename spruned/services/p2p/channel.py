import asyncio
from io import BytesIO

import typing

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
        self._getdata_listeners = dict()
        self._getdata_lock = asyncio.Lock()
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
        response = await self.msg('getdata', response_message, request_message)
        return response

    async def msg(self, message: str, name: str, *request_messages: InvItem):
        await self._getdata_lock.acquire()
        try:
            if name not in self._getdata_listeners:
                self._getdata_listeners[name] = asyncio.Future()
                self.send_msg(message, items=request_messages)
            return await self._getdata_listeners[name]
        finally:
            self._getdata_lock.locked() and self._getdata_lock.release()

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
        if resp_name in self._getdata_listeners:
            self._getdata_listeners[resp_name].set_result(data)
            self._getdata_listeners.pop(resp_name, None)
            return
        return {name: data}

    def _evaluate_block_on_pending_responses(self, name, data):
        data_bytes: bytes = data[name].getvalue()
        header = data_bytes[:80]
        block_hash = blockheader_to_blockhash(header)
        resp_name = f'{name}|{block_hash[::-1]}'
        if resp_name in self._getdata_listeners:
            self._getdata_listeners[resp_name].set_result(data_bytes)
            self._getdata_listeners.pop(resp_name, None)
            return
        return {name: BytesIO(data_bytes)}

    def _fire_callback(self, name: str, data: typing.Dict):
        if any(map(lambda f: f.startswith(f'{name}|'), self._getdata_listeners)):
            if name == 'block':
                data = self._evaluate_block_on_pending_responses(name, data)
            elif name == 'merkleblock':
                data = self._evaluate_merkleblock_on_pending_responses(name, data)

        if not data:  # event handled by the custom handlers
            return
        elif name in self._getdata_listeners:
            self._getdata_listeners[name].set_result(data)
            self._getdata_listeners.pop(name, None)
        elif name in self._events_callbacks:
            self._events_callbacks[name](self, name, data)
        else:
            Logger.p2p.error('UNKOWN MESSAGE - %s - %s', name, data)

