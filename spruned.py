from spruned.application import tools
tools.load_config()

import asyncio
from spruned.application.logging_factory import Logger
from spruned.builder import blocks_reactor, headers_reactor, jsonrpc_server, repository, cache

if __name__ == '__main__':  # pragma: no cover
    try:
        loop = asyncio.get_event_loop()
        Logger.leveldb.debug('Ensuring integrity of the storage, and tracking missing items')
        try:
            asyncio.wait_for(repository.ensure_integrity(), timeout=30)
        except asyncio.TimeoutError:
            Logger.cache.error('There must be an error in storage, 30 seconds to check are too many')
        Logger.leveldb.debug('Checking cache limits')
        try:
            asyncio.wait_for(asyncio.gather(cache.check()), timeout=10)
        except asyncio.TimeoutError:
            Logger.cache.error('There must be an error in cache, 10 seconds to check are too many')
        headers_reactor.add_on_best_height_hit_callbacks(blocks_reactor.start())
        headers_reactor.add_on_best_height_hit_callbacks(blocks_reactor.bootstrap_blocks())
        loop.create_task(headers_reactor.start())
        loop.create_task(jsonrpc_server.start())
        loop.create_task(cache.lurk())
        loop.run_forever()
    finally:
        pass
