import asyncio
import base64
import time
import typing
from json import JSONDecodeError

import aiohttp
import json


class JSONClient:
    def __init__(self, user, password, host, port):
        self.url = "http://{}:{}".format(host, port)
        self._auth = 'Basic %s' % base64.b64encode(user + b':' + password).decode()

    async def _call(self, method: str, params: typing.List=None, jsonRes=True):
        payload = {
            "method": method,
            "params": params,
            "jsonrpc": "2.0",
            "id": 1,
        }
        async with aiohttp.ClientSession(conn_timeout=10) as session:
            start = time.time()
            response = await session.post(
                self.url,
                data=json.dumps(payload),
                headers={'content-type': 'application/json', 'Authorization': self._auth},
            )
        if jsonRes:
            try:
                return (await response.json()).get('result')
            except JSONDecodeError as e:
                raise e
        else:
            return response.content


async def getblock_test(cli, bestheight=50000):
    blhash = None
    while not blhash:
        blhash = await cli._call('getblockhash', [bestheight])
        if not blhash:
            await asyncio.sleep(1)
        else:
            raise ValueError
    while 1:
        block = await cli._call('getblock', [blhash])
        if block:
            blhash = block['previousblockhash']
        else:
            await asyncio.sleep(5)

if __name__ == '__main__':
    cli = JSONClient(b'rpcuser', b'password', 'localhost', 8332)
    loop = asyncio.get_event_loop()
    bestheight = 500000
    loop.run_until_complete(getblock_test(cli, bestheight=bestheight))
