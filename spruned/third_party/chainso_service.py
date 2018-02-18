from spruned import settings
from spruned.service.abstract import RPCAPIService
from spruned.third_party.http_client import HTTPClient
from spruned.tools import normalize_transaction


class ChainSoService(RPCAPIService):
    def __init__(self, coin):
        self._coin_url = {
            settings.Network.BITCOIN: 'BTC/'
        }[coin]
        self.client = HTTPClient(baseurl='https://chain.so/api/v2/')

    def getrawtransaction(self, txid, **_):
        data = self.client.get('get_tx/' + self._coin_url + txid)
        assert data['status'] == 'success', data
        _r = {
            'rawtx': normalize_transaction(data['data']['tx_hex']),
            'blockhash': data['data']['blockhash'],
            'blockheight': None,
            'confirmations': data['data']['confirmations'],
            'time': data['data']['time'],
            'txid': txid,
            'source': 'chainso'
        }
        _r['size'] = len(_r['rawtx'])
        return _r

    def getblock(self, blockhash):
        print('getblock from %s' % self.__class__)
        data = self.client.get('get_block/' + self._coin_url + blockhash)
        assert data['status'] == 'success', data
        d = data['data']
        return {
            'hash': d['blockhash'],
            'confirmations': d['confirmations'],
            'strippedsize': None,
            'size': d['size'],
            'weight': None,
            'height': None,
            'version': None,
            'versionHex': None,
            'merkleroot': d['merkleroot'],
            'tx': d['txs'],
            'time': d['time'],
            'mediantime': None,
            'nonce': None,
            'bits': None,
            'difficulty': int(float(d['mining_difficulty'])),
            'chainwork': None,
            'previousblockhash': d['previous_blockhash'],
            'nextblockhash': d['next_blockhash'],
            'source': 'chainso'
        }

    def getblockheader(self, blockhash):
        raise NotImplementedError
