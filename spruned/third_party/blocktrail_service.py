from spruned import settings
from spruned.service.abstract import RPCAPIService
from datetime import datetime
from spruned.third_party.http_client import HTTPClient


class BlocktrailService(RPCAPIService):
    def __init__(self, coin, api_key=None, httpclient=HTTPClient):
        coin_url = {
            settings.NETWORK.BITCOIN: 'btc/'
        }[coin]
        self.client = httpclient(baseurl='https://api.blocktrail.com/v1/' + coin_url)
        assert api_key is not None
        self.api_key = api_key
        self._e_d = datetime(1970, 1, 1)

    def getrawtransaction(self, txid, **_):
        url = 'transaction/' + txid + '?api_key=' + self.api_key
        data = self.client.get(url)
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
            'txid': txid,
            'source': 'blocktrail'
        }

    def getblock(self, blockhash):
        url = 'block/' + blockhash + '?api_key=' + self.api_key
        d = self.client.get(url)
        _c = d['block_time'].split('+')[0]
        utc_time = datetime.strptime(_c, "%Y-%m-%dT%H:%M:%S")
        epoch_time = int((utc_time - self._e_d).total_seconds())
        return {
            'hash': d['hash'],
            'confirmations': d['confirmations'],
            'strippedsize': None,
            'size': d['byte_size'],
            'weight': None,
            'height': None,
            'version': str(d['version']),
            'versionHex': None,
            'merkleroot': d['merkleroot'],
            'tx': None,
            'time': epoch_time,
            'mediantime': None,
            'nonce': None,
            'bits': None,
            'difficulty': int(float(d['difficulty'])),
            'chainwork': None,
            'previousblockhash': d['prev_block'],
            'nextblockhash': d['next_block'],
            'source': 'blocktrail'
        }

    def getblockheader(self, blockhash):
        raise NotImplementedError
