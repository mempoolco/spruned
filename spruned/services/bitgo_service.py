from spruned import settings
from spruned.abstracts import RPCAPIService
from spruned.services.http_client import HTTPClient
from spruned.tools import normalize_transaction


class BitGoService(RPCAPIService):
    def __init__(self, coin, http_client=HTTPClient):
        assert coin == settings.Network.BITCOIN
        self.client = http_client(baseurl='https://www.bitgo.com/api/v1/')

    def getrawtransaction(self, txid, **_):
        data = self.client.get('tx/' + txid)
        return data and {
            'rawtx': normalize_transaction(data['hex']),
            'blockhash': data['blockhash'],
            'size': None,
            'txid': data['id'],
            'source': 'bitgo'
        }

    def getblock(self, blockhash):
        print('getblock from %s' % self.__class__)
        data = self.client.get('block/' + blockhash)
        return data and {
            'source': 'bitgo',
            'hash': data['id'],
            'tx': data['transactions'],
        }

    @property
    def available(self):
        return True
