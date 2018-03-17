from spruned.application import settings
from spruned.application.abstracts import RPCAPIService
from spruned.application.logging_factory import Logger
from spruned.services.http_client import HTTPClient


class ChainFlyerService(RPCAPIService):
    def __init__(self, coin):
        assert coin == settings.Network.BITCOIN
        self.client = HTTPClient(baseurl='https://chainflyer.bitflyer.jp/v1/')
        self.throttling_error_codes = []

    async def getrawtransaction(self, txid, **_):
        """
        data = await self.get('tx/' + txid)
        return data and {
            'rawtx': None,
            'blockhash': None,
            'size': data['size'],
            'txid': data['tx_hash'],
            'source': 'chainflyer'
        }
        """
        pass

    async def getblock(self, blockhash):
        Logger.third_party.debug('getblock from %s' % self.__class__)
        data = await self.get('block/' + blockhash)
        return data and {
            'source': 'chainflyer',
            'hash': data['block_hash'],
            'tx': data['tx_hashes'],
        }

    async def gettxout(self, txid: str, index: int):
        """
        chainflyer doesn't provide enough informations to build gettxout
        """
        pass
