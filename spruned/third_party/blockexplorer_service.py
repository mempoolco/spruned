from spruned import settings
from spruned.service.abstract import RPCAPIService
from spruned.third_party.http_client import HTTPClient


class BlockexplorerService(RPCAPIService):
    def __init__(self, coin, httpclient=HTTPClient):
        assert coin == settings.Network.BITCOIN
        self.client = httpclient(baseurl='https://blockexplorer.com/api/')

    def getrawtransaction(self, txid, **_):
        data = self.client.get('tx/' + txid)
        if not data:
            return
        return {
            'rawtx': None,
            'blockhash': data['blockhash'],
            'txid': txid,
            'source': 'blockexplorer.com'
        }

    def getblock(self, blockhash):
        print('getblock from %s' % self.__class__)
        data = self.client.get('block/' + blockhash)
        if not data:
            return
        return {
            'source': 'blockexplorer.com',
            'hash': data['hash'],
            'tx': None
        }
