import requests
from bitcoin import deserialize, serialize

from spruned import settings
from spruned.service.abstract import RPCAPIService
from datetime import datetime

from spruned.tools import purge_from_empty_segwit


class BitGoService(RPCAPIService):
    def __init__(self, coin):
        self.client = requests.Session()
        assert coin == settings.Network.BITCOIN
        self.BASE = 'https://www.bitgo.com/api/v1/'
        self._e_d = datetime(1970, 1, 1)

    def getrawtransaction(self, txid, **_):
        url = self.BASE + 'tx/' + txid
        response = self.client.get(url)
        response.raise_for_status()
        data = response.json()
        _c = data['date'].split('.')[0]
        utc_time = datetime.strptime(_c, "%Y-%m-%dT%H:%M:%S")
        epoch_time = int((utc_time - self._e_d).total_seconds())

        return {
            'rawtx': purge_from_empty_segwit(data['hex']),
            'blockhash': data['blockhash'],
            'blockheight': data['height'],
            'confirmations': data['confirmations'],
            'time': epoch_time,
            'size': None,
            'txid': data['id'],
            'source': 'bitgo'
        }

    def getblock(self, blockhash):
        url = self.BASE + 'block/' + blockhash
        response = self.client.get(url)
        response.raise_for_status()
        data = response.json()
        d = data
        _c = data['date'].split('.')[0]
        utc_time = datetime.strptime(_c, "%Y-%m-%dT%H:%M:%S")
        epoch_time = int((utc_time - self._e_d).total_seconds())
        return {
            'source': 'bitgo',
            'hash': d['id'],
            'confirmations': None,
            'strippedsize': None,
            'size': None,
            'weight': None,
            'height': d['height'],
            'version': str(d['version']),
            'versionHex': None,
            'merkleroot': d['merkleRoot'],
            'tx': d['transactions'],
            'time': epoch_time,
            'mediantime': None,
            'nonce': d['nonce'],
            'bits': None,
            'difficulty': None,
            'chainwork': d['chainWork'],
            'previousblockhash': d['previous'],
            'nextblockhash': None
        }

    def getblockheader(self, blockhash):
        raise NotImplementedError