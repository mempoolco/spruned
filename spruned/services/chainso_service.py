from typing import Dict

from spruned.application import settings, exceptions
from spruned.application.abstracts import RPCAPIService
from spruned.application.logging_factory import Logger
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
        Logger.third_party.debug('getblock from %s' % self.__class__)
        data = await self.get('get_block/' + self._coin_url + blockhash)
        return data and data.get('success') and {
            'source': 'chainso',
            'hash': data['data']['blockhash'],
            'tx': data['data']['txs']
        }

    async def gettxout(self, txid: str, index: int):
        """
        https://chain.so/api#get-is-tx-output-spent
        """
        pass


if __name__ == '__main__':
    import asyncio
    loop = asyncio.get_event_loop()
    api = ChainSoService(settings.NETWORK)
    print(loop.run_until_complete(api.gettxout('8e4c29e2c37a1107f732492a94a94197bbbc6f93aa97b7b3e58852d42680b923', 0)))
