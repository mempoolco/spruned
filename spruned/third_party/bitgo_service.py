from spruned import settings
from spruned.service.abstract import RPCAPIService
from datetime import datetime
from spruned.third_party.http_client import HTTPClient
from spruned.tools import normalize_transaction


class BitGoService(RPCAPIService):
    def __init__(self, coin, http_client=HTTPClient):
        assert coin == settings.Network.BITCOIN
        self._e_d = datetime(1970, 1, 1)
        self.client = http_client(baseurl='https://www.bitgo.com/api/v1/')

    def getrawtransaction(self, txid, **_):
        data = self.client.get('tx/' + txid)
        _c = data['date'].split('.')[0]
        utc_time = datetime.strptime(_c, "%Y-%m-%dT%H:%M:%S")
        epoch_time = int((utc_time - self._e_d).total_seconds())

        return {
            'rawtx': normalize_transaction(data['hex']),
            'blockhash': data['blockhash'],
            'blockheight': data['height'],
            'confirmations': data['confirmations'],
            'time': epoch_time,
            'size': None,
            'txid': data['id'],
            'source': 'bitgo'
        }

    def getblock(self, blockhash):
        data = self.client.get('block/' + blockhash)
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
