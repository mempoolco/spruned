import base64
import typing
from json import JSONDecodeError

import aiohttp
import json


class JSONClient:
    def __init__(self, user, password, host, port):
        self.url = "http://{}:{}".format(host, port)
        self._auth = 'Basic %s' % base64.b64encode(user + b':' + password).decode()

    async def call(self, method: str, params: typing.List=None, jsonRes=True):
        payload = {
            "method": method,
            "params": params,
            "jsonrpc": "2.0",
            "id": 1,
        }
        async with aiohttp.ClientSession(conn_timeout=10) as session:
            response = await session.post(
                self.url,
                data=json.dumps(payload),
                headers={'content-type': 'application/json', 'Authorization': self._auth},
            )
        if jsonRes:
            try:
                return (await response.json())
            except JSONDecodeError as e:
                raise e
        else:
            return response.content
