from typing import Dict

from spruned.application import settings
from spruned.application.abstracts import RPCAPIService
from spruned.services.http_client import HTTPClient


class BitpayService(RPCAPIService):
    def __init__(self, coin, httpclient=HTTPClient, utxo_tracker=None):
        assert coin == settings.Network.BITCOIN
        self.client = httpclient(baseurl='https://insight.bitpay.com/api/')
        self.throttling_error_codes = []
        self.utxo_tracker = utxo_tracker

    async def getrawtransaction(self, txid, **_):
        data = await self.get('tx/' + txid)
        return data and {
            'rawtx': None,
            'blockhash': data['blockhash'],
            'size': None,
            'txid': txid,
            'source': 'insight.bitpay.com'
        }

    async def getblock(self, blockhash):
        print('getblock from %s' % self.__class__)
        data = await self.get('block/' + blockhash)
        return data and {
            'source': 'blockexplorer.com',
            'hash': data['hash'],
            'tx': None
        }

    def _track_spents(self, data):
        for i, _v in enumerate(data.get('vout', [])):
            _v.get('spentTxId') and self.utxo_tracker.track_utxo_spent(
                data['txid'],
                i,
                spent_by=_v.get('spentTxId'),
                spent_at_index=_v.get('spentIndex'),
                spent_at_height=_v.get('spentAtHeight')
            )

    @staticmethod
    def _format_txout(data: Dict, index: int):
        return {
            "in_block": data.get("blockhash"),
            "in_block_height": data.get("blockheight"),
            "value_satoshi": int(float(data["vout"][index]["value"])*10**8),
            "script_hex": data["vout"][index]["scriptPubKey"]["hex"],
            "script_asm": data["vout"][index]["scriptPubKey"]["asm"],
            "script_type": data["vout"][index]["scriptPubKey"]["type"],
            "addresses": data["vout"][index]["scriptPubKey"].get("addresses", []),
            "unspent": not bool(data["vout"][index]["spentTxId"])
        }

    async def gettxout(self, txid, index):
        data = await self.get('tx/' + txid)
        if not data or index >= len(data.get('vout', [])):
            return
        self.utxo_tracker and self._track_spents(data)
        return self._format_txout(data, index)


if __name__ == '__main__':
    import asyncio
    loop = asyncio.get_event_loop()
    api = BitpayService(settings.NETWORK)
    print(loop.run_until_complete(api.gettxout('8e4c29e2c37a1107f732492a94a94197bbbc6f93aa97b7b3e58852d42680b923', 0)))
