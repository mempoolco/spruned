import functools
from spruned.application.storage import StorageFileInterface


class CacheFileInterface(StorageFileInterface):
    def __init__(self, directory, cache_limit=None, compress=True):
        super().__init__(directory, cache_limit=cache_limit, compress=compress)


def cache_transaction(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        cacheargs = ''.join(args[1:])
        cached = False
        res = None
        if args[0].cache:
            cache_res = args[0].cache.get('getrawtransaction', cacheargs)
            if cache_res:
                res = cache_res
                cached = True
        if res is None:
            res = await func(*args, **kwargs)
            cached = False

        if res and args[0].cache and not cached:
            best_height = args[0].repository.get_best_header().get('block_height')
            args[0].current_best_height = best_height
            confirmed = False
            if res.get('blockhash'):
                header = args[0].repository.get_block_header(res['blockhash'])
                if header:
                    res['confirmations'] = best_height - header['block_height']
                    if res['confirmations'] > 3:
                        args[0].cache.set('getrawtransaction', res['txid'], res)
                        confirmed = True

        if kwargs.get('verbose'):
            raise NotImplementedError
        else:
            return res and res['rawtx']
    return wrapper
