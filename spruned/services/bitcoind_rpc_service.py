import base64
import json
from json import JSONDecodeError
import requests


class BitcoindRPCClient:
    def __init__(self, user, password, bitcoind_url):
        self.bitcoind_url = bitcoind_url
        self._auth = 'Basic %s' % base64.b64encode(user + b':' + password).decode()

    def _call(self, method: str, *params, jsonRes=True):
        payload = {
            "method": method,
            "params": params,
            "jsonrpc": "2.0",
            "id": 0,
        }
        response = requests.post(
            self.bitcoind_url,
            data=json.dumps(payload),
            headers={'content-type': 'application/json', 'Authorization': self._auth}
        )
        if jsonRes:
            try:
                return response.json().get('result')
            except JSONDecodeError as e:
                print('Error decoding: %s' % e)
        else:
            return response.content

    def getblockhash(self, height):
        return self._call('getblockhash', height)

    def getblock(self, blockhash):
        res = self._call('getblock', blockhash)
        return None  # FIXME

    def decoderawtransaction(self, txid):
        res = self._call('decoderawtransaction', txid)
        return res

    def getbestheight(self):
        res = self._call('getblockchaininfo')
        return res['headers']

    def getblockheader(self, blockhash):
        return self._call('getblockheader', blockhash)

