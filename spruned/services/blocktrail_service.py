from spruned.application import settings
from spruned.application.abstracts import RPCAPIService
from spruned.services.http_client import HTTPClient
from spruned.application import exceptions


class BlocktrailService(RPCAPIService):
    def __init__(self, coin, api_key=None, httpclient=HTTPClient):
        coin_url = {
            settings.NETWORK.BITCOIN: 'btc/'
        }[coin]
        self.client = httpclient(baseurl='https://api.blocktrail.com/v1/' + coin_url)
        assert api_key is not None
        self.api_key = api_key

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
        url = 'transaction/' + txid + '?api_key=' + self.api_key
        data = await self.get(url)
        return data and {
            'source': 'blocktrail',
            'rawtx': None,
            'blockhash': data['block_hash'],
            'txid': txid
        }

    async def getblock(self, blockhash):
        print('getblock from %s' % self.__class__)
        url = 'block/' + blockhash + '?api_key=' + self.api_key
        data = await self.get(url)
        return data and {
            'source': 'blocktrail',
            'hash': data['hash'],
            'confirmations': data['confirmations'],
            'tx': None
        }
