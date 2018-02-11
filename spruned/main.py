import json

from spruned.service import spruned_vo_service
from spruned.third_party.blocktrail_service import BlocktrailService
from spruned.third_party.chainso_service import ChainSoService
from spruned.third_party.blockcypher_service import BlockCypherService
from spruned import settings
from spruned.third_party.spruned_service import SprunedHTTPService

spruned_http_service = SprunedHTTPService(settings.NETWORK, settings.SPRUNED_SERVICE_URL)
chainso = ChainSoService(settings.NETWORK)
blocktrail = BlocktrailService(settings.NETWORK, api_key=settings.BLOCKTRAIL_API_KEY)
blockcypher = BlockCypherService(settings.NETWORK)

service = spruned_vo_service.SprunedVOService(min_sources=2)
service.add_primary_service(chainso)
service.add_service(blocktrail)
service.add_service(blockcypher)


def jsonprint(d):
    print(json.dumps(d, indent=4))


if __name__ == '__main__':
    jsonprint(
        service.getrawtransaction('6e52a2b72cf65dcde87fcccf1d19eb9cc45ea9cf554068039a17cb68bae2da8d')
    )
    jsonprint(
        service.getblock('00000000000000000051c5e3c951e4874f28245a191fe4d06abce1edff9631c1')
    )
