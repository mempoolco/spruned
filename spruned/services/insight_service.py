from typing import Dict
from spruned.application.abstracts import RPCAPIService
from spruned.application.logging_factory import Logger


class InsightService(RPCAPIService):
    client = None
    throttling_error_codes = []
    utxo_tracker = None

    async def getrawtransaction(self, txid, **_):
        data = await self.get('tx/' + txid)
        return data and {
            'rawtx': None,
            'blockhash': data['blockhash'],
            'txid': txid,
            "source": self.__class__.__name__.replace("Service", "").lower(),
        }

    async def getblock(self, blockhash):   # pragma: no cover
        pass
        """
        Logger.third_party.debug('getblock from %s' % self.__class__)
        data = await self.get('block/' + blockhash)
        return data and {
            "source": self.__class__.__name__.replace("Service", "").lower(),
            'hash': data['hash'],
            'tx': None
        }
        """

    def _track_spents(self, data):
        for i, _v in enumerate(data.get('vout', [])):
            _v.get('spentTxId') and self.utxo_tracker.track_utxo_spent(
                data['txid'],
                i,
                spent_by=_v.get('spentTxId'),
                spent_at_index=_v.get('spentIndex'),
                spent_at_height=_v.get('spentAtHeight')
            )

    def _format_txout(self, data: Dict, index: int):
        return {
            "source": self.__class__.__name__.replace("Service", "").lower(),
            "in_block": data["blockhash"],
            "in_block_height": data["blockheight"],
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