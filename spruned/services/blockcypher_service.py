from spruned import settings
from spruned.abstracts import RPCAPIService
from datetime import datetime
import time
from spruned.services.http_client import HTTPClient
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
        return data and {
            'rawtx': normalize_transaction(data['hex']),
            'blockhash': data['block_hash'],
            'size': None,
            'txid': txid,
            'source': 'blockcypher'
        }

    def getblock(self, blockhash):
        print('getblock from %s' % self.__class__)
        _s = 0
        _l = 500
        d = None
        while 1:
            query = '?txstart=%s&limit=%s' % (_s, _l)
            query = self.api_token and query + '&token=%s' % self.api_token or query
            res = self.client.get('blocks/' + blockhash + query)
            if not res:
                return
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
        return {
            'source': 'blockcypher',
            'hash': d['hash'],
            'tx': d['txids']
        }

    @property
    def available(self):
        return True
