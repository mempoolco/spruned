from spruned.application import settings
from spruned.application.abstracts import RPCAPIService
from spruned.services.http_client import HTTPClient


class BitpayService(RPCAPIService):
    def __init__(self, coin, httpclient=HTTPClient):
        assert coin == settings.Network.BITCOIN
        self.client = httpclient(baseurl='https://insight.bitpay.com/api/')
        self.throttling_error_codes = []

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

    async def gettxout(self, txid, height):
        """
        https: // insight.bitpay.com / api / tx / 356ab5efacf7f9324f4bbb4c5bfbecf4df1f731acb70d20932c086478e875516
        return enough infos on the output to have a gettxout api
        """
        pass
