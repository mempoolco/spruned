def build():  # pragma: no cover

    from spruned.application import tools
    tools.load_config()
    from spruned.services.thirdparty_service import builder as third_party_services_builder
    from spruned.application import spruned_vo_service, settings, database
    from spruned.application.cache import CacheFileInterface
    from spruned.application.jsonrpc_server import JSONRPCServer
    from spruned.daemon.electrod.electrod_reactor import build_electrod
    from spruned.application.headers_repository import HeadersSQLiteRepository

    # system
    headers_repository = HeadersSQLiteRepository(database.session)
    cache = CacheFileInterface(settings.CACHE_ADDRESS)
    storage = CacheFileInterface(settings.STORAGE_ADDRESS, compress=False)
    electrod_daemon, electrod_service = build_electrod(
        headers_repository, settings.NETWORK, settings.ELECTROD_CONNECTIONS
    )

    # deprecate me !
    third_pary_services = third_party_services_builder()


    # vo service
    service = spruned_vo_service.SprunedVOService(
        electrod_service,
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
    return electrod_daemon, jsonrpc_server


electrod_daemon, jsonrpc_server = build()  # pragma: no cover
