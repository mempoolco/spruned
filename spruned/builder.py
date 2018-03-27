from spruned.application.cache import CacheAgent
from spruned.repositories.repository import Repository
from spruned import settings
from spruned.daemon.tasks.blocks_reactor import BlocksReactor
from spruned.daemon.tasks.headers_reactor import HeadersReactor
from spruned.application import spruned_vo_service
from spruned.application.jsonrpc_server import JSONRPCServer
from spruned.daemon.electrod import build as electrod_builder
from spruned.daemon.p2p import build as p2p_builder

electrod_connectionpool, electrod_interface = electrod_builder(settings.NETWORK)
p2p_connectionpool, p2p_interface = p2p_builder(settings.NETWORK)

repository = Repository.instance()
cache = CacheAgent(repository, settings.CACHE_SIZE)
repository.set_cache(cache)

service = spruned_vo_service.SprunedVOService(
    electrod_interface,
    p2p_interface,
    repository=repository,
    cache=cache
)

jsonrpc_server = JSONRPCServer(
    settings.JSONRPCSERVER_HOST,
    settings.JSONRPCSERVER_PORT,
    settings.JSONRPCSERVER_USER,
    settings.JSONRPCSERVER_PASSWORD
)
jsonrpc_server.set_vo_service(service)
headers_reactor = HeadersReactor(repository.headers, electrod_interface)
blocks_reactor = BlocksReactor(repository, p2p_interface, prune=settings.BOOTSTRAP_BLOCKS)
