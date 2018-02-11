import requests
from bitcoin import deserialize, serialize

from spruned import settings
from spruned.service.abstract import RPCAPIService


class ChainSoService(RPCAPIService):
    def __init__(self, coin):
        self.client = requests.Session()
        self.BASE = 'https://chain.so/api/v2/'
        self.coins = {
            settings.Network.BITCOIN: 'BTC/'
        }
        self.coin = self.coins[coin]

    def getrawtransaction(self, txid, **_):
        url = self.BASE + 'get_tx/' + self.coin + txid
        response = self.client.get(url)
        response.raise_for_status()
        data = response.json()
        assert data['status'] == 'success', data
        tx = deserialize(data['data']['tx_hex'])
        tx['segwit'] = True
        tx = serialize(tx)
        return {
            'rawtx': tx,
            'blockhash': data['data']['blockhash'],
            'blockheight': None,
            'confirmations': data['data']['confirmations'],
            'time': data['data']['time'],
            'size': data['data']['size'],
            'txid': txid
        }

    def getblock(self, blockhash):
        url = self.BASE + 'get_block/' + self.coin + blockhash
        response = self.client.get(url)
        response.raise_for_status()
        data = response.json()
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
            'difficulty': d['mining_difficulty'],
            'chainwork': None,
            'previousblockhash': d['previous_blockhash'],
            'nextblockhash': d['next_blockhash']
        }

    def getblockheader(self, blockhash):
        raise NotImplementedError
