import concurrent
import functools
import json
import typing
import random
from spruned.service.abstract import RPCAPIService, CacheInterface
import asyncio
import concurrent.futures
from spruned.service.connectrum_service import ConnectrumService


def cache_block(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        bitcoind = args[0].bitcoind
        res = func(*args, **kwargs)
        best_height = bitcoind.getbestheight()
        args[0].current_best_height = best_height

        # block case
        if res.get('height'):
            height = res['height']
            res['confirmations'] = best_height - height
            if res['confirmations'] > 3:
                args[0].cache.set('getblock', res['hash'], res)
        return res
    return wrapper


def cache_transaction(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        bitcoind = args[0].bitcoind
        res = func(*args, **kwargs)
        best_height = bitcoind.getbestheight()
        args[0].current_best_height = best_height
        confirmed = False
        if res.get('blockhash'):
            blockheader = bitcoind.getblockheader(res['blockhash'])
            if blockheader.get('height'):
                res['confirmations'] = best_height - blockheader['height']
                if res['confirmations'] > 3:
                    args[0].cache.set('getrawtransaction', res['txid'], res)
                    confirmed = True

        if kwargs.get('verbose'):
            data = bitcoind.decoderawtransaction(res['rawtx'])
            if confirmed:
                data['confirmations'] = blockheader['confirmations']
                data['time'] = blockheader['time']
            return data
        else:
            return res['rawtx']
    return wrapper


def maybe_cached(method):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **_):
            if args[0].cache:
                cacheargs = ''.join(args[1:])
                _d = args[0].cache.get(method, cacheargs)
                if _d:
                    print('Cache hit for %s - %s' % (method, cacheargs))
                    return _d
                else:
                    print('Cache miss for %s - %s' % (method, cacheargs))
            return func(*args)
        return wrapper
    return decorator


class SprunedVOService(RPCAPIService):
    def __init__(self, min_sources=3, bitcoind=None, cache=None):
        self.sources = []
        self.primary = []
        self.cache = cache
        self.min_sources = min_sources
        self.bitcoind = bitcoind
        self.current_best_height = None
        self.electrum = None  # type: ConnectrumService

    def available(self):
        raise NotImplementedError

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
                response and responses.append(response)

    @staticmethod
    def _join_data(data: typing.List[typing.Dict]) -> typing.Dict:
        def _get_key(_k, _data):
            _dd = [x[_k] for x in data if x.get(_k) is not None]
            for i, x in enumerate(_dd):
                if i < len(_dd) - 2:
                    if _k in ('source', 'time', 'confirmations'):
                        pass
                    elif _k == 'size' and data[i].get('hash'):
                        return min([x, _dd[i + 1]])
                    else:
                        try:
                            assert x == _dd[i+1], \
                                (_k, x, _dd[i+1], data[i]['source'], data[i+1]['source'])
                        except AssertionError:
                            print(json.dumps(data, indent=4))
                            return None
            return _dd and _dd[0] or None

        for k in data:
            assert isinstance(k, dict), k
        res = data[0]
        for k, v in res.items():
            res[k] = _get_key(k, data)
        res['source'] = ', '.join(x['source'] for x in data)
        return res

    @staticmethod
    def _is_complete(data):
        if data.get('txid'):
            if not data.get('blockhash') or not data.get('rawtx'):
                return False
        elif data.get('hash'):
            if not data.get('tx'):
                return False
        return data

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

    def _pick_sources(self, _exclude_services=None):
        excluded = _exclude_services and [x.__class__.__name__ for x in _exclude_services] or []
        res = []
        maxiter = 50
        i = 0
        while len(res) < self.min_sources:
            i += 1
            if i > maxiter:
                return res
            c = random.choice(self.sources)
            c not in res and (not excluded or c.__class__.__name__ not in excluded) and c.available and res.append(c)
        for p in self.primary:
            excluded is None or (p.__class__.__name__ not in excluded) and res.append(p)
        return res

    def _verify_transaction(self, transaction: dict):
        if not self.bitcoind:
            return 1
        assert transaction['blockheight']
        blockhash = self.bitcoind.getblockhash(transaction['blockheight'])
        assert blockhash == transaction['blockhash']
        block = self.getblock(blockhash)
        assert transaction['txid'] in block['tx']
        return 1

    @cache_block
    @maybe_cached('getblock')
    def getblock(self, blockhash: str, try_from_bitcoind=False):
        block = self._getblock(blockhash, try_from_bitcoind)
        return block

    def _verify_block_with_local_header(self, block):
        # TODO, validate txs list with local merkle root
        header = self.bitcoind.getblockheader(block['hash'])
        block['version'] = header['version']
        block['time'] = header['time']
        block['versionHex'] = header['versionHex']
        block['mediantime'] = header['mediantime']
        block['nonce'] = header['nonce']
        block['bits'] = header['bits']
        block['difficulty'] = header['difficulty']
        block['chainwork'] = header['chainwork']
        block['previousblockhash'] = header['previousblockhash']

        if header.get('height'):
            block['height'] = header['height']
        if header.get('nextblockhash'):
            block['nextblockhash'] = header['nextblockhash']
        block.pop('confirmations', None)
        return block

    def _getblock(self, blockhash: str, try_from_bitcoind=False, _res=None, _exclude_services=None, _r=0):
        assert _r < 10
        _exclude_services = _exclude_services or []
        block = self.bitcoind and try_from_bitcoind and self.bitcoind.getblock(blockhash)
        if not block:
            services = self._pick_sources(_exclude_services)
            res = _res or []
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._async_call(services, 'getblock', blockhash, res))
            if not res:
                _exclude_services.extend(services)
                return self._getblock(blockhash, _res=res, _exclude_services=services)
            block = self._join_data(res)
            if not self._is_complete(block):
                _exclude_services.extend(services)
                return self._getblock(blockhash, _res=res, _exclude_services=services)
            self._verify_block_with_local_header(block)
        return block

    @cache_transaction
    @maybe_cached('getrawtransaction')
    def getrawtransaction(self, txid: str, verbose=False):
        return self._getrawtransaction(txid, verbose=verbose)

    def _getrawtransaction(self, txid: str, verbose=False, _res=None, _exclude_services=None, _r=0):
        res = _res or []
        _exclude_services = _exclude_services or []
        services = self._pick_sources(_exclude_services)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(self._async_call(services, 'getrawtransaction', txid, res))
        if not res:
            _exclude_services.extend(services)
            return self._getrawtransaction(txid, verbose=verbose, _res=res, _exclude_services=_exclude_services)
        transaction = self._join_data(res)
        if not transaction.get('rawtx') and self.electrum:
            rawtransaction = self.electrum.getrawtransaction(txid)
            if rawtransaction:
                transaction['rawtx'] = rawtransaction['rawtx']
                transaction['source'] += ', electrum'
        if not self._is_complete(transaction):
            _exclude_services.extend(services)
            return self._getrawtransaction(txid, verbose=verbose, _res=res, _exclude_services=_exclude_services)
        assert transaction['rawtx']
        return transaction
