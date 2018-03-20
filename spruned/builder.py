from spruned.application import tools
tools.load_config()

from spruned.application.blocks_repository import BlocksRepository
from spruned.daemon.tasks.blocks_reactor import BlocksReactor
from spruned.daemon.tasks.headers_reactor import HeadersReactor
from spruned.services.thirdparty_service import builder as third_party_services_builder
from spruned.application import spruned_vo_service, settings, database
from spruned.application.cache import CacheFileInterface
from spruned.application.jsonrpc_server import JSONRPCServer
from spruned.application.headers_repository import HeadersSQLiteRepository
from spruned.daemon.electrod import build as electrod_builder
from spruned.daemon.p2p import build as p2p_builder

electrod_connectionpool, electrod_interface = electrod_builder(settings.NETWORK)
p2p_connectionpool, p2p_interface = p2p_builder(settings.NETWORK)

headers_repository = HeadersSQLiteRepository(database.session)
blocks_repository = BlocksRepository(settings.STORAGE_ADDRESS)

cache = CacheFileInterface(settings.CACHE_ADDRESS)

third_pary_services = third_party_services_builder()
service = spruned_vo_service.SprunedVOService(
    electrod_interface,
    p2p_interface,
    cache=cache,
    repository=headers_repository
)
service.add_source(third_pary_services)
jsonrpc_server = JSONRPCServer(
    settings.JSONRPCSERVER_HOST,
    settings.JSONRPCSERVER_PORT,
    settings.JSONRPCSERVER_USER,
    settings.JSONRPCSERVER_PASSWORD
)
jsonrpc_server.set_vo_service(service)
headers_reactor = HeadersReactor(headers_repository, electrod_interface)
blocks_reactor = BlocksReactor(blocks_repository, headers_repository, p2p_interface)
