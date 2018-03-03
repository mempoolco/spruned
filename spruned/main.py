import asyncio
import json
from spruned.application import spruned_vo_service, settings
from spruned.application.logging_factory import Logger
from spruned.application.cache import CacheFileInterface
from spruned.daemon.electrod.electrod_reactor import build_electrod
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
electrod_daemon = build_electrod(settings.NETWORK, settings.ELECTROD_SOCKET, settings.ELECTROD_CONCURRENCY)
electrod_service = ElectrodService(settings.ELECTROD_SOCKET)


# services
chainso = ChainSoService(settings.NETWORK)
blocktrail = settings.BLOCKTRAIL_API_KEY and BlocktrailService(settings.NETWORK, api_key=settings.BLOCKTRAIL_API_KEY)
blockcypher = BlockCypherService(settings.NETWORK, api_token=settings.BLOCKCYPHER_API_TOKEN)
bitgo = BitGoService(settings.NETWORK)
chainflyer = ChainFlyerService(settings.NETWORK)
blockexplorer = BlockexplorerService(settings.NETWORK)
bitpay = BitpayService(settings.NETWORK)


# vo service
service = spruned_vo_service.SprunedVOService(electrod_service, cache=cache)
service.add_source(chainso)
service.add_source(bitgo)
service.add_source(blockexplorer)
service.add_source(blockcypher)
blocktrail and service.add_source(blocktrail)
service.add_source(chainflyer)
service.add_source(bitpay)


def jsonprint(d):
    print(json.dumps(d, indent=4))


async def test_apis():
    print('sleeping')
    await asyncio.sleep(5)
    print('starting')
    try:
        Logger.root.debug('Starting sPRUNED')
        blockhash = "0000000000000000000612c2915991d1ed779380bbfacd8082cd24bb588861b9"
        while 1:
            print('Requesting Block hash: %s' % blockhash)
            block = await service.getblock(blockhash)
            for txid in block['tx'][:10]:
                print(await service.getrawtransaction(txid))
            blockhash = block['previousblockhash']
    except:
        Logger.root.exception('Exception in sPRUNED main')
        raise
    finally:
        Logger.root.debug('Spruned exit')

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(electrod_daemon.start())
    loop.create_task(test_apis())
    loop.run_forever()
