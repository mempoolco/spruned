from spruned.application import settings
from spruned.application.abstracts import RPCAPIService
from spruned.services.http_client import HTTPClient
from spruned.application import exceptions


class ChainFlyerService(RPCAPIService):
    def __init__(self, coin):
        assert coin == settings.Network.BITCOIN
        self.client = HTTPClient(baseurl='https://chainflyer.bitflyer.jp/v1/')

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
            'blockhash': None,
            'size': data['size'],
            'txid': data['tx_hash'],
            'source': 'chainflyer'
        }

    async def getblock(self, blockhash):
        print('getblock from %s' % self.__class__)
        data = await self.get('block/' + blockhash)
        return data and {
            'source': 'chainflyer',
            'hash': data['block_hash'],
            'tx': data['tx_hashes'],
        }
