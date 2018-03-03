import json
from spruned.application import spruned_vo_service, settings
from spruned.application.logging_factory import Logger
from spruned.application.cache import CacheFileInterface
from spruned.services.bitcoind_rpc_service import BitcoindRPCClient

from spruned.services.bitgo_service import BitGoService
from spruned.services.bitpay_service import BitpayService
from spruned.services.blockexplorer_service import BlockexplorerService
from spruned.services.blocktrail_service import BlocktrailService
from spruned.services.chainflyer_service import ChainFlyerService
from spruned.services.chainso_service import ChainSoService
from spruned.services.blockcypher_service import BlockCypherService
from spruned.services.electrod_service import ElectrodService

# system

cache = CacheFileInterface(settings.CACHE_ADDRESS)
storage = CacheFileInterface(settings.STORAGE_ADDRESS, compress=False)

# services

bitcoind = BitcoindRPCClient(settings.BITCOIND_USER, settings.BITCOIND_PASS, settings.BITCOIND_URL)
chainso = ChainSoService(settings.NETWORK)
blocktrail = settings.BLOCKTRAIL_API_KEY and BlocktrailService(settings.NETWORK, api_key=settings.BLOCKTRAIL_API_KEY)
blockcypher = BlockCypherService(settings.NETWORK, api_token=settings.BLOCKCYPHER_API_TOKEN)
bitgo = BitGoService(settings.NETWORK)
chainflyer = ChainFlyerService(settings.NETWORK)
blockexplorer = BlockexplorerService(settings.NETWORK)
bitpay = BitpayService(settings.NETWORK)

# electrum

electrum_service = settings.ENABLE_ELECTRUM and ElectrodService(settings.NETWORK)

# vo service

service = spruned_vo_service.SprunedVOService(min_sources=settings.MIN_DATA_SOURCES, bitcoind=bitcoind, cache=cache)
service.add_source(chainso)
service.add_source(bitgo)
service.add_source(blockexplorer)
service.add_source(blockcypher)
blocktrail and service.add_source(blocktrail)
service.add_source(chainflyer)
service.add_source(bitpay)
service.electrum = electrum_service


def jsonprint(d):
    print(json.dumps(d, indent=4))


if __name__ == '__main__':
    try:
        Logger.root.debug('Starting sPRUNED')
        electrum_service and electrum_service.connect()
        print(service.getrawtransaction('991789bbe7f09bb06d5539b0aae6e194e4f09e42819861c81bee1d81e2021a8d', verbose=1))
        blockhash = "0000000000000000000e5b215c3b4704fcc7b9c8b1eccbcad1251061f20b91a8"
        blockhash = "0000000000000000000612c2915991d1ed779380bbfacd8082cd24bb588861b9"
        block = service.getblock(blockhash)
        while 1:
            block = service.getblock(blockhash)
            for txid in block['tx'][:10]:
                print(service.getrawtransaction(txid))
            blockhash = block['previousblockhash']
    except:
        Logger.root.exception('Exception in sPRUNED main')
    finally:
        electrum_service and electrum_service.disconnect()
        Logger.root.debug('Spruned exit')

