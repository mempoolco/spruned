import json

from spruned.service.bitcoind_rpc_client import BitcoindRPCClient
from spruned.third_party.blocktrail_service import BlocktrailService
from spruned.third_party.chainso_service import ChainSoService
from spruned.third_party.blockcypher_service import BlockCypherService
from spruned import settings, spruned_vo_service
from spruned.third_party.spruned_service import SprunedHTTPService

spruned_http_service = SprunedHTTPService(settings.NETWORK, settings.SPRUNED_SERVICE_URL)
chainso = ChainSoService(settings.NETWORK)
blocktrail = settings.BLOCKTRAIL_API_KEY and BlocktrailService(settings.NETWORK, api_key=settings.BLOCKTRAIL_API_KEY)
blockcypher = BlockCypherService(settings.NETWORK, api_token=settings.BLOCKCYPHER_API_TOKEN)
bitcoind = BitcoindRPCClient(settings.BITCOIND_USER, settings.BITCOIND_PASS, settings.BITCOIND_URL)

service = spruned_vo_service.SprunedVOService(min_sources=3, bitcoind=bitcoind)
service.add_primary_source(chainso)
blocktrail and service.add_source(blocktrail)
service.add_source(blockcypher)


def jsonprint(d):
    print(json.dumps(d, indent=4))


if __name__ == '__main__':
    jsonprint(
        service.getrawtransaction('6e52a2b72cf65dcde87fcccf1d19eb9cc45ea9cf554068039a17cb68bae2da8d')
    )
    jsonprint(
        service.getblock('00000000000000000051c5e3c951e4874f28245a191fe4d06abce1edff9631c1')
    )
