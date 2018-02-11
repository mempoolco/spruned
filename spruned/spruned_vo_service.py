import functools
import typing
import random
from spruned.service.abstract import RPCAPIService, CacheInterface


def maybe_cached(method):
    @functools.wraps
    def wrapper(*args, **kwargs):
        if args[0].cache:
            _d = args[0].cache.get(method, ''.join(args[1:]))
            if _d:
                return _d
        return wrapper(args, kwargs)
    return wrapper


class SprunedVOService(RPCAPIService):
    MAX_TIME_DIVERGENCE_TOLERANCE_BETWEEN_SERVICES = 10

    def __init__(self, min_sources=3, bitcoind=None):
        self.sources = []
        self.primary = []
        self.cache = None
        self.min_sources = min_sources
        self.bitcoind = bitcoind

    def _join_data(self, data: typing.List[typing.Dict]) -> typing.Dict:
        def _get_key(_k, _data):
            _dd = [x[_k] for x in data if x.get(_k) is not None]
            for i, x in enumerate(_dd):
                if i < len(_dd) - 2:
                    if _k == 'time':
                        assert abs(x - _dd[i+1]) < self.MAX_TIME_DIVERGENCE_TOLERANCE_BETWEEN_SERVICES
                    else:
                        assert x == _dd[i+1], (x, _dd[i+1], data)
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
        assert transaction['txid'] in block['tx']
        return 1

    @maybe_cached('getblock')
    def getblock(self, blockhash: str):
        block = self.bitcoind and self.bitcoind.getblock(blockhash)
        if not block:
            res = []
            for service in self._pick_sources():
                res.append(service.getblock(blockhash))
            block = self._join_data(res)
        block['confirmations'] > 3 and self.cache and self.cache.set('getblock', blockhash, block)
        return block

    @maybe_cached('getrawtransaction')
    def getrawtransaction(self, txid: str, verbose=False):
        res = []
        for service in self._pick_sources():
            res.append(service.getrawtransaction(txid))
        transaction = self._join_data(res)
        transaction['blockhash'] and self._verify_transaction(transaction)
        self.cache and \
            transaction['blockhash'] and \
            self.cache.get('getblock', transaction['blockhash']) and \
            self.cache.set('getrawtransaction', txid, transaction)
        if verbose:
            raise NotImplementedError
        return transaction['rawtx']

    @maybe_cached('getblockheader')
    def getblockheader(self, blockhash, verbose=True):
        raise NotImplementedError

