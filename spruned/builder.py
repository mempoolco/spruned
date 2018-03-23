from spruned.application import tools
from spruned.repositories.blockchain_repository import BlockchainRepository
from spruned.repositories.repository import Repository

tools.load_config()

from spruned.daemon.tasks.blocks_reactor import BlocksReactor
from spruned.daemon.tasks.headers_reactor import HeadersReactor
from spruned.services.thirdparty_service import builder as third_party_services_builder
from spruned.application import spruned_vo_service, settings
from spruned.application.jsonrpc_server import JSONRPCServer
from spruned.daemon.electrod import build as electrod_builder
from spruned.daemon.p2p import build as p2p_builder
from spruned.application.database import cache_ldb

electrod_connectionpool, electrod_interface = electrod_builder(settings.NETWORK)
p2p_connectionpool, p2p_interface = p2p_builder(settings.NETWORK)

repository = Repository.instance()

cache = BlockchainRepository(
    cache_ldb, settings.LEVELDB_CACHE_SLUG, settings.LEVELDB_CACHE_ADDRESS, limit=50*1024*1024
)

third_party_services = third_party_services_builder()
service = spruned_vo_service.SprunedVOService(
    electrod_interface,
    p2p_interface,
    repository=repository,
    cache=cache
)
service.add_source(third_party_services)
jsonrpc_server = JSONRPCServer(
    settings.JSONRPCSERVER_HOST,
    settings.JSONRPCSERVER_PORT,
    settings.JSONRPCSERVER_USER,
    settings.JSONRPCSERVER_PASSWORD
)
jsonrpc_server.set_vo_service(service)
headers_reactor = HeadersReactor(repository.headers, electrod_interface)
blocks_reactor = BlocksReactor(repository, p2p_interface)
