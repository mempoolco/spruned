import asyncio

from spruned.application.logging_factory import Logger
from spruned.builder import blocks_reactor, headers_reactor, jsonrpc_server, repository, cache

if __name__ == '__main__':  # pragma: no cover
    try:
        loop = asyncio.get_event_loop()
        Logger.leveldb.debug('Ensuring integrity of the storage, and tracking missing items')
        asyncio.wait_for(repository.ensure_integrity())
        Logger.leveldb.debug('Checking cache limits')
        asyncio.wait_for(cache.check())
        loop.create_task(headers_reactor.start())
        loop.create_task(blocks_reactor.start())
        loop.create_task(jsonrpc_server.start())
        loop.create_task(cache.lurk())
        loop.run_forever()
    finally:
        pass
