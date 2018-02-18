import json

import time

import sys

from spruned import settings, spruned_vo_service
from spruned.service.bitcoind_rpc_client import BitcoindRPCClient
from spruned.service.file_cache_interface import FileCacheInterface
from spruned.third_party.bitgo_service import BitGoService
from spruned.third_party.bitpay_service import BitpayService
from spruned.third_party.blockexplorer_service import BlockexplorerService
from spruned.third_party.blocktrail_service import BlocktrailService
from spruned.third_party.chainflyer_service import ChainFlyerService
from spruned.third_party.chainso_service import ChainSoService
from spruned.third_party.blockcypher_service import BlockCypherService

#from spruned.third_party.spruned_service import SprunedHTTPService
#spruned_http_service = SprunedHTTPService(settings.NETWORK, settings.SPRUNED_SERVICE_URL)

cache = FileCacheInterface(settings.CACHE_ADDRESS)
bitcoind = BitcoindRPCClient(settings.BITCOIND_USER, settings.BITCOIND_PASS, settings.BITCOIND_URL)
chainso = ChainSoService(settings.NETWORK)
blocktrail = settings.BLOCKTRAIL_API_KEY and BlocktrailService(settings.NETWORK, api_key=settings.BLOCKTRAIL_API_KEY)
blockcypher = BlockCypherService(settings.NETWORK, api_token=settings.BLOCKCYPHER_API_TOKEN)
bitgo = BitGoService(settings.NETWORK)
chainflyer = ChainFlyerService(settings.NETWORK)
blockexplorer = BlockexplorerService(settings.NETWORK)
bitpay = BitpayService(settings.NETWORK)

service = spruned_vo_service.SprunedVOService(min_sources=settings.MIN_DATA_SOURCES, bitcoind=bitcoind, cache=cache)
service.add_source(chainso)
service.add_source(bitgo)
service.add_source(blockexplorer)
service.add_source(blockcypher)
blocktrail and service.add_source(blocktrail)
service.add_source(chainflyer)
service.add_source(bitpay)


def jsonprint(d):
    print(json.dumps(d, indent=4))


if __name__ == '__main__':
    blockhash = "00000000000000000009fd0c45ae65ff7ac277f05521e6bc19ba08c4f78d0922"
    block = service.getblock(blockhash)
    while 1:
        block = service.getblock(blockhash)
        for txid in block['tx'][:10]:
            print(service.getrawtransaction(txid, verbose=1))
            time.sleep(0.1)
        time.sleep(0.5)

