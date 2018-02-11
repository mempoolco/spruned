import requests

from spruned import settings
from spruned.service.abstract import RPCAPIService
from datetime import datetime


class ChainFlyerService(RPCAPIService):
    def __init__(self, coin):
        self.client = requests.Session()
        assert coin == settings.Network.BITCOIN
        self.BASE = 'https://chainflyer.bitflyer.jp/v1/'
        self._e_d = datetime(1970, 1, 1)

    def getrawtransaction(self, txid, **_):
        url = self.BASE + 'tx/' + txid
        response = self.client.get(url)
        response.raise_for_status()
        data = response.json()
        return {
            'rawtx': None,
            'blockhash': None,
            'blockheight': data['block_height'],
            'confirmations': data['confirmed'],
            'time': None,
            'size': data['size'],
            'txid': data['tx_hash'],
            'source': 'chainflyer'
        }

    def getblock(self, blockhash):
        url = self.BASE + 'block/' + blockhash
        response = self.client.get(url)
        response.raise_for_status()
        data = response.json()
        d = data
        _c = data['timestamp']
        utc_time = datetime.strptime(_c, "%Y-%m-%dT%H:%M:%SZ")
        epoch_time = int((utc_time - self._e_d).total_seconds())
        return {
            'hash': d['block_hash'],
            'confirmations': None,
            'strippedsize': None,
            'size': None,
            'weight': None,
            'height': d['height'],
            'version': d['version'],
            'versionHex': None,
            'merkleroot': d['merkle_root'],
            'tx': d['tx_hashes'],
            'time': epoch_time,
            'mediantime': None,
            'nonce': d['nonce'],
            'bits': d['bits'],
            'difficulty': None,
            'chainwork': None,
            'previousblockhash': d['prev_block'],
            'nextblockhash': None,
            'source': 'chainflyer'
        }

    def getblockheader(self, blockhash):
        raise NotImplementedError