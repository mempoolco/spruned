from spruned.application import settings
from spruned.application.abstracts import RPCAPIService
from spruned.application.tools import normalize_transaction
from spruned.services.http_client import HTTPClient


class BitGoService(RPCAPIService):
    def __init__(self, coin, http_client=HTTPClient):
        assert coin == settings.Network.BITCOIN
        self.client = http_client(baseurl='https://www.bitgo.com/api/v1/')

    async def getrawtransaction(self, txid, **_):
        data = await self.client.get('tx/' + txid)
        return data and {
            'rawtx': normalize_transaction(data['hex']),
            'blockhash': data['blockhash'],
            'size': None,
            'txid': data['id'],
            'source': 'bitgo'
        }

    async def getblock(self, blockhash):
        print('getblock from %s' % self.__class__)
        data = await self.client.get('block/' + blockhash)
        return data and {
            'source': 'bitgo',
            'hash': data['id'],
            'tx': data['transactions'],
        }

    @property
    def available(self):
        return True
