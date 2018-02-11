import json
from spruned import settings, spruned_vo_service
from spruned.service.bitcoind_rpc_client import BitcoindRPCClient

from spruned.third_party.bitgo_service import BitGoService
from spruned.third_party.blockexplorer_service import BlockexplorerService
from spruned.third_party.blocktrail_service import BlocktrailService
from spruned.third_party.chainflyer_service import ChainFlyerService
from spruned.third_party.chainso_service import ChainSoService
from spruned.third_party.blockcypher_service import BlockCypherService

#from spruned.third_party.spruned_service import SprunedHTTPService
#spruned_http_service = SprunedHTTPService(settings.NETWORK, settings.SPRUNED_SERVICE_URL)

bitcoind = BitcoindRPCClient(settings.BITCOIND_USER, settings.BITCOIND_PASS, settings.BITCOIND_URL)
chainso = ChainSoService(settings.NETWORK)
blocktrail = settings.BLOCKTRAIL_API_KEY and BlocktrailService(settings.NETWORK, api_key=settings.BLOCKTRAIL_API_KEY)
blockcypher = BlockCypherService(settings.NETWORK, api_token=settings.BLOCKCYPHER_API_TOKEN)
bitgo = BitGoService(settings.NETWORK)
chainflyer = ChainFlyerService(settings.NETWORK)
blockexplorer = BlockexplorerService(settings.NETWORK)

service = spruned_vo_service.SprunedVOService(min_sources=settings.MIN_DATA_SOURCES, bitcoind=bitcoind)
service.add_primary_source(chainso)
service.add_source(bitgo)
service.add_source(blockexplorer)
service.add_source(blockcypher)
blocktrail and service.add_source(blocktrail)
service.add_source(chainflyer)


def jsonprint(d):
    print(json.dumps(d, indent=4))


if __name__ == '__main__':
    jsonprint(
        service.getrawtransaction('6e52a2b72cf65dcde87fcccf1d19eb9cc45ea9cf554068039a17cb68bae2da8d')
    )
    jsonprint(
        service.getblock('00000000000000000051c5e3c951e4874f28245a191fe4d06abce1edff9631c1')
    )
