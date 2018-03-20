from datetime import datetime
import time
from typing import Dict
from spruned.application import settings
from spruned.application.abstracts import RPCAPIService
from spruned.application.logging_factory import Logger
from spruned.application.tools import normalize_transaction
from spruned.services.http_client import HTTPClient


class BlockCypherService(RPCAPIService):
    def __init__(self, coin, api_token=None, httpclient=HTTPClient, utxo_tracker=None):
        coin_url = {
            settings.Network.BITCOIN: 'btc/main/',
            settings.Network.BITCOIN_TESTNET: 'btc/testnet/'
        }[coin]
        self.client = httpclient(baseurl='https://api.blockcypher.com/v1/' + coin_url)
        self._e_d = datetime(1970, 1, 1)
        self.api_token = api_token
        self.throttling_error_codes = []
        self.utxo_tracker = utxo_tracker

    async def getrawtransaction(self, txid, **_):
        query = '?includeHex=1&limit=1'
        query = self.api_token and query + '&token=%s' % self.api_token or query
        data = await self.get('txs/' + txid + query)
        return data and {
            'rawtx': normalize_transaction(data['hex']),
            'blockhash': data['block_hash'],
            'size': None,
            'txid': txid,
            'source': 'blockcypher'
        }

    def _track_spents(self, data):
        for i, _v in enumerate(data.get('vout', [])):
            _v.get('spent_by') and self.utxo_tracker.track_utxo_spent(
                data['txid'],
                i,
                spent_by=_v.get('spent_by')
            )

    @staticmethod
    def _normalize_scripttype(script_type):
        return {
            "pay-to-pubkey-hash": "pubkeyhash",
            "pay-to-script-hash": "scripthash"
        }[script_type]
        # this is broken and needs to be extended

    def _format_txout(self, data: Dict, index: int):
        return {
            "in_block": data.get("block_hash"),
            "in_block_height": data.get("block_height"),
            "value_satoshi": data["outputs"][index]["value"],
            "script_hex": data["outputs"][index]["script"],
            "script_asm": None,
            "script_type": self._normalize_scripttype(data["outputs"][index]["script_type"]),
            "addresses": data["outputs"][index].get("addresses", []),
            "unspent": not bool(data["outputs"][index].get("spent_by", False))
        }

    async def gettxout(self, txid: str, index: int):
        query = '?includeHex=1&limit=1'
        query = self.api_token and query + '&token=%s' % self.api_token or query
        data = await self.get('txs/' + txid + query)
        if not data or index >= len(data.get('outputs', [])):
            return
        self.utxo_tracker and self._track_spents(data)
        return self._format_txout(data, index)
