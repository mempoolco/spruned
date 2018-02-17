import concurrent
import functools
import json
import typing
import random
from spruned.service.abstract import RPCAPIService, CacheInterface
import asyncio
import concurrent.futures


def maybe_cached(method):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **_):
            if args[0].cache:
                _d = args[0].cache.get(method, ''.join(args[1:]))
                if _d:
                    return _d
            return func(*args)
        return wrapper
    return decorator


class SprunedVOService(RPCAPIService):
    MAX_TIME_DIVERGENCE_TOLERANCE_BETWEEN_SERVICES = 60

    def __init__(self, min_sources=3, bitcoind=None, cache=None):
        self.sources = []
        self.primary = []
        self.cache = cache
        self.min_sources = min_sources
        self.bitcoind = bitcoind

    @staticmethod
    async def _async_call(services, call, blockhash, responses):
        calls = [getattr(service, call) for service in services]
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            loop = asyncio.get_event_loop()
            futures = [
                loop.run_in_executor(
                    executor,
                    call,
                    blockhash
                )
                for call in calls
            ]
            for response in await asyncio.gather(*futures):
                responses.append(response)

    def _join_data(self, data: typing.List[typing.Dict]) -> typing.Dict:
        def _get_key(_k, _data):
            _dd = [x[_k] for x in data if x.get(_k) is not None]
            for i, x in enumerate(_dd):
                if i < len(_dd) - 2:
                    if _k == 'time':
                        assert abs(x - _dd[i+1]) < self.MAX_TIME_DIVERGENCE_TOLERANCE_BETWEEN_SERVICES, (x, _dd[i+1])
                    elif _k == 'confirmations':
                        return max([x, _dd[i+1]])
                    elif _k == 'source':
                        pass
                    elif _k == 'size' and data[i].get('hash'):
                        # Some explorers have segwit adjusted size, some not, until we're sure we can always
                        # obtain this data
                        # we skip the segwit block size
                        return min([x, _dd[i + 1]])
                    else:
                        try:
                            assert x == _dd[i+1], \
                                (_k, x, _dd[i+1], data[i]['source'], data[i+1]['source'])
                        except AssertionError:
                            print(json.dumps(data, indent=4))
                            raise
            return _dd and _dd[0] or None

        assert len(data) >= self.min_sources
        for k in data:
            assert isinstance(k, dict), k
        res = data[0]
        for k, v in res.items():
            if v is None:
                res[k] = _get_key(k, data[1:])
            else:
                assert v == _get_key(k, data[1:])
        res['source'] = ', '.join(x['source'] for x in data)
        return res

    def _get_from_cache(self, *a):
        if self.cache:
            data = self.cache.get(a[0], a[1])
            if data:
                return data

    def add_cache(self, cache: CacheInterface):
        assert isinstance(cache, CacheInterface)
        self.cache = cache

    def add_source(self, service: RPCAPIService):
        assert isinstance(service, RPCAPIService)
        self.sources.append(service)

    def add_primary_source(self, service: RPCAPIService):
        assert isinstance(service, RPCAPIService)
        self.primary.append(service)

    def _pick_sources(self):
        res = []
        max = 50
        i = 0
        while len(res) + len(self.primary) < self.min_sources:
            i += 1
            assert i < max
            _c = random.choice(self.sources)
            _c not in res and res.append(_c)
        return res + self.primary

    def _verify_transaction(self, transaction: dict):
        if not self.bitcoind:
            return 1
        assert transaction['blockheight']
        blockhash = self.bitcoind.getblockhash(transaction['blockheight'])
        assert blockhash == transaction['blockhash']
        block = self.getblock(blockhash)
        assert transaction['txid'] in block['tx'] # FIXME add merkle proof on local headers
        return 1

    @maybe_cached('getblock')
    def getblock(self, blockhash: str, try_from_bitcoind=False):
        block = self.bitcoind and try_from_bitcoind and self.bitcoind.getblock(blockhash)
        if not block:
            services = self._pick_sources()
            res = []
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self._async_call(services, 'getblock', blockhash, res))
            block = self._join_data(res)
        block['confirmations'] > 3 and self.cache and self.cache.set('getblock', blockhash, block)
        return block

    @maybe_cached('getrawtransaction')
    def getrawtransaction(self, txid: str, verbose=False):
        res = []
        services = self._pick_sources()
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._async_call(services, 'getrawtransaction', txid, res))
        transaction = self._join_data(res)
        transaction['blockhash'] and self._verify_transaction(transaction)
        self.cache and \
            transaction['blockhash'] and \
            self.cache.get('getblock', transaction['blockhash']) and \
            self.cache.set('getrawtransaction', txid, transaction)
        if verbose:
            return self.bitcoind.decoderawtransaction(transaction['rawtx'])
        return transaction['rawtx']

    @maybe_cached('getblockheader')
    def getblockheader(self, blockhash, verbose=True):
        raise NotImplementedError

