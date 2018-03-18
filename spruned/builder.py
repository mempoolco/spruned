def build():  # pragma: no cover

    from spruned.application import tools
    tools.load_config()
    from spruned.services.thirdparty_service import builder as third_party_services_builder
    from spruned.application import spruned_vo_service, settings, database
    from spruned.application.cache import CacheFileInterface
    from spruned.application.jsonrpc_server import JSONRPCServer
    from spruned.daemon.builder import build_reactor_and_daemon, build_electrod_interface
    from spruned.application.headers_repository import HeadersSQLiteRepository

    headers_repository = HeadersSQLiteRepository(database.session)
    cache = CacheFileInterface(settings.CACHE_ADDRESS)
    interface = build_electrod_interface(connections=settings.ELECTROD_CONNECTIONS)
    headers_reactor, daemon_service = build_reactor_and_daemon(headers_repository, interface)
    third_pary_services = third_party_services_builder()
    service = spruned_vo_service.SprunedVOService(
        daemon_service,
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
    return headers_reactor, jsonrpc_server


daemon, jsonrpc_server = build()  # pragma: no cover
