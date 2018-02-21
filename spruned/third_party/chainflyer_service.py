from spruned import settings
from spruned.service.abstract import RPCAPIService
from spruned.third_party.http_client import HTTPClient


class ChainFlyerService(RPCAPIService):
    def __init__(self, coin):
        assert coin == settings.Network.BITCOIN
        self.client = HTTPClient(baseurl='https://chainflyer.bitflyer.jp/v1/')

    def getrawtransaction(self, txid, **_):
        data = self.client.get('tx/' + txid)
        return data and {
            'rawtx': None,
            'blockhash': None,
            'size': data['size'],
            'txid': data['tx_hash'],
            'source': 'chainflyer'
        }

    def getblock(self, blockhash):
        print('getblock from %s' % self.__class__)
        data = self.client.get('block/' + blockhash)
        return data and {
            'source': 'chainflyer',
            'hash': data['block_hash'],
            'tx': data['tx_hashes'],
        }

    @property
    def available(self):
        return True
