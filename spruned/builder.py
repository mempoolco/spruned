from spruned.application.tools import load_config
load_config()

from spruned.application import spruned_vo_service, settings
from spruned.application.cache import CacheFileInterface
from spruned.application.jsonrpc_server import JSONRPCServer

from spruned.daemon import database
from spruned.daemon.electrod.electrod_reactor import build_electrod
from spruned.services.bitgo_service import BitGoService
from spruned.services.bitpay_service import BitpayService
from spruned.services.blockexplorer_service import BlockexplorerService
from spruned.services.blocktrail_service import BlocktrailService
from spruned.services.chainflyer_service import ChainFlyerService
from spruned.services.chainso_service import ChainSoService
from spruned.services.blockcypher_service import BlockCypherService
from spruned.services.localbitcoins_service import LocalbitcoinsService
from spruned.daemon.electrod.headers_repository import HeadersSQLiteRepository

# system
headers_repository = HeadersSQLiteRepository(database.session)
cache = CacheFileInterface(settings.CACHE_ADDRESS)
storage = CacheFileInterface(settings.STORAGE_ADDRESS, compress=False)
electrod_daemon, electrod_service = build_electrod(
    headers_repository, settings.NETWORK, settings.ELECTROD_CONCURRENCY
)


# services
chainso = ChainSoService(settings.NETWORK)
blocktrail = settings.BLOCKTRAIL_API_KEY and BlocktrailService(settings.NETWORK, api_key=settings.BLOCKTRAIL_API_KEY)
blockcypher = BlockCypherService(settings.NETWORK, api_token=settings.BLOCKCYPHER_API_TOKEN)
bitgo = BitGoService(settings.NETWORK)
chainflyer = ChainFlyerService(settings.NETWORK)
blockexplorer = BlockexplorerService(settings.NETWORK)
bitpay = BitpayService(settings.NETWORK)
localbitcoins = LocalbitcoinsService(settings.NETWORK)


# vo service
service = spruned_vo_service.SprunedVOService(electrod_service, cache=cache, repository=headers_repository)
service.add_source(chainso)
service.add_source(bitgo)
service.add_source(blockexplorer)
service.add_source(blockcypher)
blocktrail and service.add_source(blocktrail)
service.add_source(chainflyer)
service.add_source(bitpay)
service.add_source(localbitcoins)

jsonrpc_server = JSONRPCServer(
    settings.JSONRPCSERVER_HOST,
    settings.JSONRPCSERVER_PORT,
    settings.JSONRPCSERVER_USER,
    settings.JSONRPCSERVER_PASSWORD
)
jsonrpc_server.set_vo_service(service)
