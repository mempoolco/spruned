from spruned.builder import headers_reactor, jsonrpc_server, p2p_interface, blocks_reactor, repository


async def main_task(loop):  # pragma: no cover
    await repository.run()
    loop.create_task(jsonrpc_server.start())
    loop.create_task(p2p_interface.start())
    loop.create_task(headers_reactor.start())
    loop.create_task(blocks_reactor.start())
    p2p_interface.pool.add_on_headers_callback(headers_reactor.on_headers)
    p2p_interface.pool.add_on_block_callback(blocks_reactor.on_block)
