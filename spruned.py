import asyncio

from spruned.application import tools
tools.load_config()

from spruned.application.tools import async_delayed_task
from spruned.application.logging_factory import Logger
from spruned.builder import blocks_reactor, headers_reactor, jsonrpc_server, repository, cache


async def main_task(loop):
    try:
        Logger.leveldb.debug('Ensuring integrity of the storage, and tracking missing items')
        try:
            await loop_check_integrity(loop)
        except asyncio.TimeoutError:
            Logger.cache.error('There must be an error in storage, 30 seconds to check are too many')
        Logger.leveldb.debug('Checking cache limits')
        try:
            asyncio.wait_for(asyncio.gather(cache.check()), timeout=30)
        except asyncio.TimeoutError:
            Logger.cache.error('There must be an error in cache, 30 seconds to check are too many')
        headers_reactor.add_on_best_height_hit_callbacks(blocks_reactor.start())
        headers_reactor.add_on_best_height_hit_callbacks(blocks_reactor.bootstrap_blocks())
        loop.create_task(headers_reactor.start())
        loop.create_task(jsonrpc_server.start())
        loop.create_task(cache.lurk())
    finally:
        pass


async def loop_check_integrity(l):
    """
    this task also prune blocks
    """
    await repository.ensure_integrity()
    l.create_task(async_delayed_task(loop_check_integrity(l), 3600))


if __name__ == '__main__':  # pragma: no cover
    main_loop = asyncio.get_event_loop()
    main_loop.create_task(main_task(main_loop))
    main_loop.run_forever()
