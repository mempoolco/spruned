from spruned.application import settings, exceptions
from spruned.application.abstracts import RPCAPIService
from spruned.services.http_client import HTTPClient


class BitpayService(RPCAPIService):
    def __init__(self, coin, httpclient=HTTPClient):
        assert coin == settings.Network.BITCOIN
        self.client = httpclient(baseurl='https://insight.bitpay.com/api/')

    async def get(self, path):
        try:
            return await self.client.get(path)
        except exceptions.HTTPClientException as e:
            from aiohttp import ClientResponseError
            cause: ClientResponseError = e.__cause__
            if isinstance(cause, ClientResponseError):
                if cause.code == 429:
                    self._increase_errors()

    async def getrawtransaction(self, txid, **_):
        data = await self.get('tx/' + txid)
        return data and {
            'rawtx': None,
            'blockhash': data['blockhash'],
            'size': None,
            'txid': txid,
            'source': 'insight.bitpay.com'
        }

    async def getblock(self, blockhash):
        print('getblock from %s' % self.__class__)
        data = await self.get('block/' + blockhash)
        return data and {
            'source': 'blockexplorer.com',
            'hash': data['hash'],
            'tx': None
        }
