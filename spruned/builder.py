from spruned.application.context import ctx as _ctx, Context
from spruned.daemon.zeromq import build_zmq


def builder(ctx: Context):  # pragma: no cover
    from spruned.application.cache import CacheAgent
    from spruned.repositories.repository import Repository
    from spruned.daemon.tasks.blocks_reactor import BlocksReactor
    from spruned.daemon.tasks.headers_reactor import HeadersReactor
    from spruned.application import spruned_vo_service
    from spruned.application.jsonrpc_server import JSONRPCServer
    from spruned.daemon.electrod import build as electrod_builder
    from spruned.daemon.bitcoin_p2p import build as p2p_builder

    electrod_connectionpool, electrod_interface = electrod_builder(ctx)
    p2p_connectionpool, p2p_interface = p2p_builder(ctx)
    repository = Repository.instance()
    cache = CacheAgent(repository, int(ctx.cache_size))
    repository.set_cache(cache)
    service = spruned_vo_service.SprunedVOService(
        electrod_interface,
        p2p_interface,
        repository=repository,
        cache_agent=cache,
        context=ctx,
        fallback_non_segwit_blocks=True
    )
    jsonrpc_server = JSONRPCServer(ctx.rpcbind, ctx.rpcport, ctx.rpcuser, ctx.rpcpassword)
    jsonrpc_server.set_vo_service(service)
    headers_reactor = HeadersReactor(repository.headers, electrod_interface)

    if ctx.mempool_size:
        from spruned.application.mempool_observer import MempoolObserver
        mempool_observer = MempoolObserver(repository, p2p_interface)
        headers_reactor.add_on_new_header_callback(mempool_observer.on_block_header)
        p2p_interface.mempool = repository.mempool
        p2p_connectionpool.add_on_transaction_callback(mempool_observer.on_transaction)
        p2p_connectionpool.add_on_transaction_hash_callback(mempool_observer.on_transaction_hash)
    else:
        mempool_observer = None
    zmq_context = zmq_observer = None
    if ctx.is_zmq_enabled():
        zmq_context, zmq_observer = build_zmq(
            ctx,
            mempool_observer,
            headers_reactor,
            ctx.mempool_size,
            service
        )
    blocks_reactor = BlocksReactor(repository, p2p_interface, keep_blocks=int(ctx.keep_blocks))
    headers_reactor.add_on_best_height_hit_persistent_callbacks(p2p_connectionpool.set_best_header)

    return jsonrpc_server, headers_reactor, blocks_reactor, repository, cache, zmq_context, zmq_observer


jsonrpc_server, headers_reactor, blocks_reactor, repository, cache, zmq_context, zmq_observer = builder(_ctx)
