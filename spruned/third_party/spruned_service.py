from pip._vendor import requests
from spruned.service.abstract import RPCAPIService
from spruned import settings


class SprunedHTTPService(RPCAPIService):
    def __init__(self, coin, url):
        self.url = url
        assert coin == settings.Network.BITCOIN
        self.client = requests.Session()

    def getrawtransaction(self, txid, verbose=False):
        url = self.url + 'getrawtransaction/' + txid
        response = self.client.get(url)
        response.raise_for_status()
        return response.json()

    def getblock(self, blockhash):
        url = self.url + 'getblock/' + blockhash
        response = self.client.get(url)
        response.raise_for_status()
        return response.json()

    def getblockheader(self, blockhash):
        raise NotImplementedError