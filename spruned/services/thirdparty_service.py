import random
from spruned.application import exceptions
from spruned.application.abstracts import RPCAPIService

# Services to avoid to obtain this information


class ThirdPartyServiceDelegate(RPCAPIService):
    """
    this class is a necessary evil to track unspents.


    at the moment.
    """
    def __init__(self):
        self._getrawtransaction_services = []
        self._gettxout_services = []
        self._getblock_services = []
        self.retries = 2

    def add_getrawtransaction_service(self, service: RPCAPIService):
        self._getrawtransaction_services.append(service)

    def add_gettxout_service(self, service: RPCAPIService):
        self._gettxout_services.append(service)

    def add_getblock_service(self, service: RPCAPIService):
        self._getblock_services.append(service)

    @property
    def getrawtransaction_services(self):
        return [ser for ser in self._getrawtransaction_services if ser.available]

    @property
    def gettxout_services(self):
        return [ser for ser in self._gettxout_services if ser.available]

    @property
    def getblock_services(self):
        return [ser for ser in self._getblock_services if ser.available]

    async def _get(self, call, *a):
        s = {
            'getblock': self.getblock_services,
            'gettxout': self.gettxout_services,
            'getrawtransaction': self.getrawtransaction_services
        }
        result = None
        i = 0
        tries = []
        while not result:
            if i > self.retries*len(s[call])*10:
                raise exceptions.ServiceException

            source = random.choice(s[call])
            if tries.count(source.__class__.__name__) > self.retries:
                i += 1
                continue

            tries.append(source.__class__.__name__)
            result = await getattr(source, call)(*a)
        return result

    async def getblock(self, blockhash: str):
        return await self._get('getblock', blockhash)

    async def getrawtransaction(self, txid: str, verbose=False):
        return await self._get('getrawtransaction', txid)

    async def gettxout(self, txid: str, index: int):
        return await self._get('gettxout', txid, index)


def builder():
    from spruned.application import settings

    from spruned.services.bitgo_service import BitGoService
    from spruned.services.bitpay_service import BitpayService
    from spruned.services.blockexplorer_service import BlockexplorerService
    from spruned.services.blocktrail_service import BlocktrailService
    from spruned.services.chainflyer_service import ChainFlyerService
    from spruned.services.chainso_service import ChainSoService
    from spruned.services.blockcypher_service import BlockCypherService
    from spruned.services.localbitcoins_service import LocalbitcoinsService

    chainso = ChainSoService(settings.NETWORK)
    blocktrail = settings.BLOCKTRAIL_API_KEY and BlocktrailService(settings.NETWORK,
                                                                   api_key=settings.BLOCKTRAIL_API_KEY)
    blockcypher = BlockCypherService(settings.NETWORK, api_token=settings.BLOCKCYPHER_API_TOKEN)
    bitgo = BitGoService(settings.NETWORK)
    chainflyer = ChainFlyerService(settings.NETWORK)
    blockexplorer = BlockexplorerService(settings.NETWORK)
    bitpay = BitpayService(settings.NETWORK)
    localbitcoins = LocalbitcoinsService(settings.NETWORK)

    third_party_service = ThirdPartyServiceDelegate()

    third_party_service.add_getblock_service(bitgo)
    third_party_service.add_getblock_service(blockcypher)
    third_party_service.add_getblock_service(chainflyer)
    third_party_service.add_getblock_service(chainso)

    third_party_service.add_gettxout_service(blockcypher)
    third_party_service.add_gettxout_service(bitpay)
    third_party_service.add_gettxout_service(blockexplorer)
    third_party_service.add_gettxout_service(localbitcoins)
    blocktrail and third_party_service.add_gettxout_service(blocktrail)

    third_party_service.add_getrawtransaction_service(bitgo)
    third_party_service.add_getrawtransaction_service(blockcypher)
    third_party_service.add_getrawtransaction_service(blockexplorer)
    blocktrail and third_party_service.add_getrawtransaction_service(blocktrail)
    third_party_service.add_getrawtransaction_service(chainso)
    third_party_service.add_getrawtransaction_service(localbitcoins)

    return third_party_service
