import requests
from bitcoin import deserialize, serialize

from spruned import settings
from spruned.service.abstract import RPCAPIService
from datetime import datetime
import time


class BlockCypherService(RPCAPIService):
    def __init__(self, coin, api_token=None):
        self.client = requests.Session()
        self.BASE = 'https://api.blockcypher.com/v1/'
        self.coin = {
            settings.Network.BITCOIN: 'btc/main/',
            settings.Network.BITCOIN_TESTNET: 'btc/testnet/'
        }[coin]
        self._e_d = datetime(1970, 1, 1)
        self.api_token = api_token

    def getrawtransaction(self, txid, **_):
        url = self.BASE + self.coin + 'txs/' + txid + '?includeHex=1&limit=1'
        url = self.api_token and url + '&token=%s' % self.api_token or url
        response = self.client.get(url)
        response.raise_for_status()
        data = response.json()
        _c = data['confirmed'].split('.')[0]
        utc_time = datetime.strptime(_c, "%Y-%m-%dT%H:%M:%S")
        epoch_time = int((utc_time - self._e_d).total_seconds())
        tx = deserialize(data['hex'])
        tx['segwit'] = True
        tx = serialize(tx)
        return {
            'rawtx': tx,
            'blockhash': data['block_hash'],
            'blockheight': data['block_height'],
            'confirmations': data['confirmations'],
            'time': epoch_time,
            'size': None,
            'txid': txid,
            'source': 'blockcypher'
        }

    def getblock(self, blockhash):
        print('getblock from blockcypher')
        _s = 0
        _l = 500
        d = None
        while 1:
            url = self.BASE + self.coin + 'blocks/' + blockhash + '?txstart=%s&limit=%s' % (_s, _l)
            url = self.api_token and url + '&token=%s' % self.api_token or url
            if not self.api_token:
                time.sleep(0.5)
            response = self.client.get(url)
            response.raise_for_status()
            res = response.json()
            if d is None:
                d = res
            else:
                d['txids'].extend(res['txids'])
            if len(res['txids']) < 500:
                break
            _s += 500
            _l += 500
        utc_time = datetime.strptime(d['time'], "%Y-%m-%dT%H:%M:%SZ")
        epoch_time = int((utc_time - self._e_d).total_seconds())
        return {
            'hash': d['hash'],
            'confirmations': None,
            'strippedsize': None,
            'size': d['size'],
            'weight': None,
            'height': d['height'],
            'version': d['ver'],
            'versionHex': None,
            'merkleroot': d['mrkl_root'],
            'tx': d['txids'],
            'time': epoch_time,
            'mediantime': None,
            'nonce': d['nonce'],
            'bits': d['bits'],
            'difficulty': None,
            'chainwork': None,
            'previousblockhash': d['prev_block'],
            'nextblockhash': None,
            'source': 'blockcypher'
        }

    def getblockheader(self, blockhash):
        raise NotImplementedError