import bitcoin
import struct
from spruned import settings
from spruned.service.abstract import RPCAPIService
from datetime import datetime
import time
from spruned.third_party.http_client import HTTPClient
from spruned.tools import normalize_transaction


class BlockCypherService(RPCAPIService):
    def __init__(self, coin, api_token=None, httpclient=HTTPClient):
        coin_url = {
            settings.Network.BITCOIN: 'btc/main/',
            settings.Network.BITCOIN_TESTNET: 'btc/testnet/'
        }[coin]
        self.client = httpclient(baseurl='https://api.blockcypher.com/v1/' + coin_url)
        self._e_d = datetime(1970, 1, 1)
        self.api_token = api_token

    def getrawtransaction(self, txid, **_):
        query = '?includeHex=1&limit=1'
        query = self.api_token and query + '&token=%s' % self.api_token or query
        data = self.client.get('txs/' + txid + query)
        _c = data['confirmed'].split('.')[0]
        utc_time = datetime.strptime(_c, "%Y-%m-%dT%H:%M:%S")
        epoch_time = int((utc_time - self._e_d).total_seconds())
        return {
            'rawtx': normalize_transaction(data['hex']),
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
            query = '?txstart=%s&limit=%s' % (_s, _l)
            query = self.api_token and query + '&token=%s' % self.api_token or query
            res = self.client.get('txs/' + blockhash + query)
            if not self.api_token:
                time.sleep(0.5)
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
            'version': str(d['ver']),
            'versionHex': None,
            'merkleroot': d['mrkl_root'],
            'tx': d['txids'],
            'time': epoch_time,
            'mediantime': None,
            'nonce': d['nonce'],
            'bits': bitcoin.safe_hexlify(struct.pack('l', d['bits'])[:4][::-1]),
            'difficulty': None,
            'chainwork': None,
            'previousblockhash': d['prev_block'],
            'nextblockhash': None,
            'source': 'blockcypher'
        }

    def getblockheader(self, blockhash):
        raise NotImplementedError
