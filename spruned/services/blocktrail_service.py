from spruned import settings
from spruned.abstracts import RPCAPIService
from spruned.services.http_client import HTTPClient


class BlocktrailService(RPCAPIService):
    def __init__(self, coin, api_key=None, httpclient=HTTPClient):
        coin_url = {
            settings.NETWORK.BITCOIN: 'btc/'
        }[coin]
        self.client = httpclient(baseurl='https://api.blocktrail.com/v1/' + coin_url)
        assert api_key is not None
        self.api_key = api_key

    def getrawtransaction(self, txid, **_):
        url = 'transaction/' + txid + '?api_key=' + self.api_key
        data = self.client.get(url)
        return data and {
            'source': 'blocktrail',
            'rawtx': None,
            'blockhash': data['block_hash'],
            'txid': txid
        }

    def getblock(self, blockhash):
        print('getblock from %s' % self.__class__)
        url = 'block/' + blockhash + '?api_key=' + self.api_key
        data = self.client.get(url)
        return data and {
            'source': 'blocktrail',
            'hash': data['hash'],
            'confirmations': data['confirmations'],
            'tx': None
        }

    @property
    def available(self):
        return True
