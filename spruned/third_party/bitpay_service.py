import requests
from spruned import settings
from spruned.service.abstract import RPCAPIService
from datetime import datetime


class BitpayService(RPCAPIService):
    def __init__(self, coin):
        self.client = requests.Session()
        self.BASE = 'https://insight.bitpay.com/api/'
        assert coin == settings.Network.BITCOIN
        self._e_d = datetime(1970, 1, 1)

    def getrawtransaction(self, txid, **_):
        url = self.BASE + 'tx/' + txid
        response = self.client.get(url)
        response.raise_for_status()
        data = response.json()
        return {
            'rawtx': None,
            'blockhash': data['blockhash'],
            'blockheight': data['blockheight'],
            'confirmations': data['confirmations'],
            'time': data['time'],
            'size': None,
            'txid': txid,
            'source': 'insight.bitpay.com'
        }

    def getblock(self, blockhash):
        url = self.BASE + 'block/' + blockhash
        response = self.client.get(url)
        response.raise_for_status()
        data = response.json()
        d = data
        return {
            'hash': d['hash'],
            'confirmations': d['confirmations'],
            'strippedsize': None,
            'size': d['size'],
            'weight': None,
            'height': d['height'],
            'version': str(d['version']),
            'versionHex': None,
            'merkleroot': d['merkleroot'],
            'tx': None,
            'time': d['time'],
            'mediantime': None,
            'nonce': d['nonce'],
            'bits': d['bits'],
            'difficulty': int(float(d['difficulty'])),
            'chainwork': None,
            'previousblockhash': d['previousblockhash'],
            'nextblockhash': d.get('nextblockhash'),
            'source': 'blockexplorer.com'
        }

    def getblockheader(self, blockhash):
        raise NotImplementedError
