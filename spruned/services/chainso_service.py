from typing import Dict

from spruned.application import settings, exceptions
from spruned.application.abstracts import RPCAPIService
from spruned.application.tools import normalize_transaction
from spruned.services.http_client import HTTPClient


class ChainSoService(RPCAPIService):
    def __init__(self, coin, utxo_tracker=None):
        self._coin_url = {
            settings.Network.BITCOIN: 'BTC/'
        }[coin]
        self.client = HTTPClient(baseurl='https://chain.so/api/v2/')
        self.errors = []
        self.errors_ttl = 5
        self.max_errors_before_downtime = 1
        self.throttling_error_codes = (429, )
        self.utxo_tracker = utxo_tracker

    async def getrawtransaction(self, txid, **_):
        data = await self.get('get_tx/' + self._coin_url + txid)
        return data and data.get('success') and {
            'rawtx': normalize_transaction(data['data']['tx_hex']),
            'blockhash': data['data']['blockhash'],
            'txid': txid,
            'source': 'chainso'
        }

    async def getblock(self, blockhash):
        print('getblock from %s' % self.__class__)
        data = await self.get('get_block/' + self._coin_url + blockhash)
        return data and data.get('success') and {
            'source': 'chainso',
            'hash': data['data']['blockhash'],
            'tx': data['data']['txs']
        }

    def _track_spents(self, data):
        data.get('is_spent') and self.utxo_tracker.track_utxo_spent(
            data['txid'],
            data['output_no'],
            spent_by=data['spent']['txid'],
            spent_at_index=data['spent']['input_no']
        )

    @staticmethod
    def _format_txout(_: Dict, __: int):
        return {
            "in_block": None,
            "in_block_height": None,
            "value_satoshi": None,
            "script_hex": None,
            "script_asm": None,
            "script_type": None,
            "addresses": None,
            "unspent": True
        }

    async def gettxout(self, txid: str, index: int):
        """
        https://chain.so/api#get-is-tx-output-spent
        """
        data = await self.get('is_tx_spent/' + self._coin_url + txid + '/' + str(index))
        if not data.get('status') == 'success':
            return
        if data['data']['is_spent']:
            self.utxo_tracker and self._track_spents(data)
        return self._format_txout(data, index)


if __name__ == '__main__':
    import asyncio
    loop = asyncio.get_event_loop()
    api = ChainSoService(settings.NETWORK)
    print(loop.run_until_complete(api.gettxout('8e4c29e2c37a1107f732492a94a94197bbbc6f93aa97b7b3e58852d42680b923', 0)))
