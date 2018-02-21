import json
import time
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
from spruned.third_party.electrum_service import ConnectrumService

cache = FileCacheInterface(settings.CACHE_ADDRESS)
bitcoind = BitcoindRPCClient(settings.BITCOIND_USER, settings.BITCOIND_PASS, settings.BITCOIND_URL)
chainso = ChainSoService(settings.NETWORK)
blocktrail = settings.BLOCKTRAIL_API_KEY and BlocktrailService(settings.NETWORK, api_key=settings.BLOCKTRAIL_API_KEY)
blockcypher = BlockCypherService(settings.NETWORK, api_token=settings.BLOCKCYPHER_API_TOKEN)
bitgo = BitGoService(settings.NETWORK)
chainflyer = ChainFlyerService(settings.NETWORK)
blockexplorer = BlockexplorerService(settings.NETWORK)
bitpay = BitpayService(settings.NETWORK)
electrum = settings.ENABLE_ELECTRUM and ConnectrumService(settings.NETWORK)


service = spruned_vo_service.SprunedVOService(min_sources=settings.MIN_DATA_SOURCES, bitcoind=bitcoind, cache=cache)
service.add_source(chainso)
service.add_source(bitgo)
service.add_source(blockexplorer)
service.add_source(blockcypher)
blocktrail and service.add_source(blocktrail)
service.add_source(chainflyer)
service.add_source(bitpay)
service.electrum = electrum


def jsonprint(d):
    print(json.dumps(d, indent=4))


if __name__ == '__main__':
    try:
        electrum and electrum.connect()
        cache.purge()
        blockhash = "0000000000000000000e5b215c3b4704fcc7b9c8b1eccbcad1251061f20b91a8"
        block = service.getblock(blockhash)
        while 1:
            block = service.getblock(blockhash)
            for txid in block['tx'][:10]:
                print(service.getrawtransaction(txid))
            blockhash = block['previousblockhash']
            time.sleep(0.5)
    finally:
        electrum and electrum.killpill()
