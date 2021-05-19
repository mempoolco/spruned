import asyncio
from io import BytesIO

import typing
from spruned.application.tools import blockheader_to_blockhash
from spruned.dependencies.pycoinnet.pycoin.InvItem import ITEM_TYPE_SEGWIT_BLOCK, InvItem, ITEM_TYPE_BLOCK


class P2PChannel:
    def __init__(self, connection: 'P2PConnection', loop=asyncio.get_event_loop()):
        self.loop = loop
        self.connection = connection
        self._events_callbacks = dict()
        self._getdata_listeners = dict()
        self._getdata_lock = asyncio.Lock()
        self._task = self.loop.create_task(self.run())

    def send_msg(self, *args, **kwargs):
        self.connection.peer.send_msg(*args, **kwargs)

    async def getblock(self, request_message: InvItem):
        response_message = {
            ITEM_TYPE_SEGWIT_BLOCK: 'block',
            ITEM_TYPE_BLOCK: 'block'
        }[request_message.item_type]
        response_message = f'{response_message}|{request_message.data}'
        response = await self.getdata(response_message, request_message)
        return response

    async def getdata(self, name: str, *request_messages: InvItem):
        await self._getdata_lock.acquire()
        try:
            if name not in self._getdata_listeners:
                self._getdata_listeners[name] = asyncio.Future()
                self.send_msg('getdata', items=request_messages)
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
        except:
            self.loop.create_task(self.connection.disconnect())
            raise

    def _evaluate_block_on_pending_responses(self, name, data):
        data_bytes: bytes = data[name].getvalue()
        header = data_bytes[:80]
        block_hash = blockheader_to_blockhash(header)
        resp_name = f'{name}|{block_hash[::-1]}'
        if resp_name in self._getdata_listeners:
            self._getdata_listeners[resp_name].set_result(data_bytes)
            self._getdata_listeners.pop(resp_name, None)
            return
        return {'block': BytesIO(data_bytes)}

    def _fire_callback(self, name: str, data: typing.Dict):
        if name == 'block' and any(map(lambda f: f.startswith('block|'), self._getdata_listeners)):
            data = self._evaluate_block_on_pending_responses(name, data)
        if not data:
            return
        elif name in self._getdata_listeners:
            self._getdata_listeners[name].set_result(data)
            self._getdata_listeners.pop(name, None)
        elif name in self._events_callbacks:
            self._events_callbacks[name](self, name, data)
