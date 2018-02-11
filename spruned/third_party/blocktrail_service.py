import requests
from spruned import settings
from spruned.service.abstract import RPCAPIService
from datetime import datetime


class BlocktrailService(RPCAPIService):
    def __init__(self, coin, api_key=None):
        self.client = requests.Session()
        self.BASE = 'https://api.blocktrail.com/v1/'
        self.coin = {
            settings.NETWORK.BITCOIN: 'btc/'
        }[coin]
        assert api_key is not None
        self.api_key = api_key
        self._e_d = datetime(1970, 1, 1)

    def getrawtransaction(self, txid, **_):
        url = self.BASE + self.coin + 'transaction/' + txid + '?api_key=' + self.api_key
        response = self.client.get(url)
        response.raise_for_status()
        data = response.json()
        _c = data['block_time'].split('+')[0]
        utc_time = datetime.strptime(_c, "%Y-%m-%dT%H:%M:%S")
        epoch_time = int((utc_time - self._e_d).total_seconds())
        return {
            'rawtx': None,
            'blockhash': data['block_hash'],
            'blockheight': data['block_height'],
            'confirmations': data['confirmations'],
            'time': epoch_time,
            'size': None,
            'txid': txid
        }

    def getblock(self, blockhash):
        url = self.BASE + self.coin + 'block/' + blockhash + '?api_key=' + self.api_key
        response = self.client.get(url)
        response.raise_for_status()
        data = response.json()
        d = data
        _c = data['block_time'].split('+')[0]
        utc_time = datetime.strptime(_c, "%Y-%m-%dT%H:%M:%S")
        epoch_time = int((utc_time - self._e_d).total_seconds())
        return {
            'hash': d['hash'],
            'confirmations': d['confirmations'],
            'strippedsize': None,
            'size': d['byte_size'],
            'weight': None,
            'height': None,
            'version': d['version'],
            'versionHex': None,
            'merkleroot': d['merkleroot'],
            'tx': None,
            'time': epoch_time,
            'mediantime': None,
            'nonce': None,
            'bits': None,
            'difficulty': d['difficulty'],
            'chainwork': None,
            'previousblockhash': d['prev_block'],
            'nextblockhash': d['next_block']
        }

    def getblockheader(self, blockhash):
        raise NotImplementedError