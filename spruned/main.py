import asyncio
import json
from spruned import settings, spruned_vo_service
from spruned.logging_factory import Logger
from spruned.service.bitcoind_rpc_client import BitcoindRPCClient
from spruned.service.cache import CacheFileInterface
from spruned.service.electrum.connectrum_client import ConnectrumClient
from spruned.third_party.bitgo_service import BitGoService
from spruned.third_party.bitpay_service import BitpayService
from spruned.third_party.blockexplorer_service import BlockexplorerService
from spruned.third_party.blocktrail_service import BlocktrailService
from spruned.third_party.chainflyer_service import ChainFlyerService
from spruned.third_party.chainso_service import ChainSoService
from spruned.third_party.blockcypher_service import BlockCypherService
from spruned.service.electrum.connectrum_service import ConnectrumService

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

connectrum_client = settings.ENABLE_ELECTRUM and ConnectrumClient(
                settings.NETWORK,
                asyncio.get_event_loop(),
                concurrency=settings.ELECTRUM_CONCURRENCY,
            )
electrum_service = settings.ENABLE_ELECTRUM and ConnectrumService(settings.NETWORK, connectrum_client)

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
        blockhash = "00000000000000000029b786fd3da3c2859a9be4807104d7e80112cdd5a33407"
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

