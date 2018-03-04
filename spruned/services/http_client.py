import asyncio
import aiohttp
import async_timeout
from spruned.application import exceptions
from spruned.application.logging_factory import Logger


class HTTPClient:
    def __init__(self, baseurl):
        self.baseurl = baseurl

    async def get(self, *a, json_response=True, **kw):
        url = self.baseurl + a[0]
        try:
            async with async_timeout.timeout(15):
                async with aiohttp.ClientSession() as session:
                    async with session as s:
                        header = {}
                        header['content-type'] = json_response and 'application/json' or 'text/html'
                        response = await s.get(url, headers=header, **kw)
                        response.raise_for_status()
                        res = await response.json() if json_response else await response.read()
        except (aiohttp.ClientResponseError, asyncio.TimeoutError, aiohttp.ClientError) as e:
            Logger.third_party.exception('Exception on call: %s' % url)
            raise exceptions.HTTPClientException from e
        return res

    async def post(self, *a, json_response=True, **kw):
        url = self.baseurl + a[0]
        try:
            async with async_timeout.timeout(10):
                async with aiohttp.ClientSession() as session:
                    async with session as s:

                            header = {}
                            header['content-type'] = json_response and 'application/json' or 'text/html'
                            response = await s.post(url, headers=header, **kw)
                            response.raise_for_status()
                            res = await response.json() if json_response else await response.read()
        except (aiohttp.ClientResponseError, asyncio.TimeoutError, aiohttp.ClientError) as e:
            Logger.third_party.exception('Exception on call: %s' % url)
            raise exceptions.HTTPClientException from e
        return res


if __name__ == '__main__':
    client = HTTPClient('http://ifconfig.co')
    loop = asyncio.get_event_loop()
    loop.run_until_complete(client.get('/json'))
