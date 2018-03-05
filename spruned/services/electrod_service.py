import asyncio
from typing import Dict

import aiomas
import async_timeout

from spruned.application.abstracts import RPCAPIService


class ElectrodService(RPCAPIService):
    def __init__(self, socketfile):
        self.socketfile = socketfile

    async def call(self, method, payload: Dict=None):
        try:
            async with async_timeout.timeout(5):
                rpc_con = await aiomas.rpc.open_connection(self.socketfile)
                call = getattr(rpc_con.remote, method)
                resp = payload is not None and await call(payload) or await call()
                await rpc_con.close()
                return resp
        except asyncio.TimeoutError:
            return

    async def getrawtransaction(self, txid, verbose=False):
        payload = {"txid": txid, "verbose": verbose}
        return await self.call("getrawtransaction", payload)

    async def getblock(self, txid, verbose=False):
        return None

    async def estimatefee(self, blocks: int):
        payload = {"blocks": blocks}
        return await self.call("estimatefee", payload)

    async def sendrawtransaction(self, rawtx: str):
        payload = {"rawtx": rawtx}
        return await self.call("sendrawtransaction", payload)

    async def listunspents(self, address: str):
        payload = {"address": address}
        return await self.call("listunspents", payload)

    @property
    def available(self) -> bool:
        return True
