from typing import Dict

from spruned.application import settings
from spruned.application.abstracts import RPCAPIService
from spruned.services.http_client import HTTPClient


class BlocktrailService(RPCAPIService):
    def __init__(self, coin, api_key=None, httpclient=HTTPClient, utxo_tracker=None):
        coin_url = {
            settings.NETWORK.BITCOIN: 'btc/'
        }[coin]
        self.client = httpclient(baseurl='https://api.blocktrail.com/v1/' + coin_url)
        assert api_key is not None
        self.api_key = api_key
        self.throttling_error_codes = []
        self.utxo_tracker = utxo_tracker

    async def getrawtransaction(self, txid, **_):
        url = 'transaction/' + txid + '?api_key=' + self.api_key
        data = await self.get(url)
        return data and {
            'source': 'blocktrail',
            'rawtx': None,
            'blockhash': data['block_hash'],
            'txid': txid
        }

    async def getblock(self, blockhash):   # pragma: no cover
        pass

    def _track_spents(self, data):
        for i, _v in enumerate(data.get('vout', [])):
            _v.get('spent_hash') and self.utxo_tracker.track_utxo_spent(
                data['hash'],
                i,
                spent_by=_v.get('spent_hash'),
                spent_at_index=_v.get('spent_index'),
            )

    @staticmethod
    def _format_txout(data: Dict, index: int):
        return {
            "in_block": data.get("blockhash"),
            "in_block_height": data.get("blockheight"),
            "value_satoshi": data["outputs"][index]["value"],
            "script_hex": data["outputs"][index]["script_hex"],
            "script_asm": data["outputs"][index]["script"],
            "script_type": data["outputs"][index]["type"],
            "addresses": [x for x in [data["outputs"][index].get("address", None)] if x is not None],
            "unspent": not bool(data["outputs"][index]["spent_hash"])
        }

    async def gettxout(self, txid, index):
        url = 'transaction/' + txid + '?api_key=' + self.api_key
        data = await self.get(url)
        if not data:
            return
        self.utxo_tracker and self._track_spents(data)
        return self._format_txout(data, index)
