import concurrent
import functools
import json
import typing
import random
from spruned.application.abstracts import RPCAPIService, StorageInterface
import asyncio
import concurrent.futures

from spruned.application.logging_factory import Logger
from spruned.services.electrod_service import ElectrodService


def cache_block(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        cacheargs = ''.join(args[1:])
        cached = False
        res = None
        if args[0].cache:
            cache_res = args[0].cache.get('getblock', cacheargs)
            if cache_res:
                res = cache_res
                cached = True

        if res is None:
            res = await func(*args, **kwargs)
            cached = False

        if res and args[0].cache and not cached and args[0].electrod:
            electrod = args[0].electrod
            best_height = await electrod.getbestheight()
            args[0].current_best_height = best_height
            height = res['height']
            res['confirmations'] = best_height - height
            if res['confirmations'] > 3:
                args[0].cache.set('getblock', res['hash'], res)
        return res
    return wrapper


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

        if res and args[0].cache and not cached and args[0].electrod:
            electrod = args[0].electrod
            best_height = await electrod.getbestheight()
            args[0].current_best_height = best_height
            confirmed = False
            if res.get('blockhash'):
                header = await electrod.getblockheader(res['blockhash'])
                if header and header.get('height'):
                    res['confirmations'] = best_height - header['height']
                    if res['confirmations'] > 3:
                        args[0].cache.set('getrawtransaction', res['txid'], res)
                        confirmed = True

        if kwargs.get('verbose'):
            raise NotImplementedError
            # Note: I have to do a PR to ElectrumX Server and today is saturday :-)
        else:
            return res and res['rawtx']
    return wrapper


class SprunedVOService(RPCAPIService):
    def __init__(self, electrod, cache=None):
        self.sources = []
        self.primary = []
        self.cache = cache
        self.electrod = electrod
        self.min_sources = 1
        self.current_best_height = None

    def available(self):
        raise NotImplementedError

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

    def add_cache(self, cache: StorageInterface):
        assert isinstance(cache, StorageInterface)
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
        # TODO
        return 1

    @cache_block
    async def getblock(self, blockhash: str):
        block = await self._getblock(blockhash)
        return block

    async def _verify_block_with_local_header(self, block):
        header = await self.electrod.getblockheader(block['hash'])
        block['version'] = header['version']
        block['time'] = header['time']
        block['versionHex'] = header['versionHex']
        block['mediantime'] = header['mediantime']
        block['nonce'] = header['nonce']
        block['bits'] = header['bits']
        block['difficulty'] = header['difficulty']
        block['chainwork'] = header['chainwork']
        block['previousblockhash'] = header['previousblockhash']
        block['height'] = header['height']
        # TODO Verify transactions tree
        if header.get('nextblockhash'):
            block['nextblockhash'] = header['nextblockhash']
        block.pop('confirmations', None)
        return block

    async def _getblock(self, blockhash: str, _res=None, _exclude_services=None, _r=0):
        assert _r < 5
        _exclude_services = _exclude_services or []
        services = self._pick_sources(_exclude_services)

        responses = _res or []
        futures = [service.getblock(blockhash) for service in services]
        for response in await asyncio.gather(*futures):
            response and responses.append(response)
        if not responses:
            _exclude_services.extend(services)
            return await self._getblock(blockhash, _res=responses, _exclude_services=services)
        block = self._join_data(responses)
        if not self._is_complete(block):
            _exclude_services.extend(services)
            return await self._getblock(blockhash, _res=responses, _exclude_services=services)
        await self._verify_block_with_local_header(block)
        return block

    @cache_transaction
    async def getrawtransaction(self, txid: str, verbose=False):
        return await self._getrawtransaction(txid, verbose=verbose)

    async def _getrawtransaction(self, txid: str, verbose=False, _res=None, _exclude_services=None, _r=0):
        if _r > 5:
            return {}
        _exclude_services = _exclude_services or []
        services = self._pick_sources(_exclude_services)
        responses = _res or []
        futures = [service.getrawtransaction(txid) for service in services]
        for response in await asyncio.gather(*futures):
            response and responses.append(response)
        if not responses:
            _exclude_services.extend(services)
            return await self._getrawtransaction(
                txid, verbose=verbose, _res=responses, _exclude_services=_exclude_services, _r=_r+1
            )
        transaction = self._join_data(responses)
        if not transaction.get('rawtx'):
            electrod_transaction = await self.electrod.getrawtransaction(txid)
            if electrod_transaction:
                transaction['rawtx'] = electrod_transaction.get('response')
                transaction['source'] += ', electrum'
        if not self._is_complete(transaction):
            _exclude_services.extend(services)
            return await self._getrawtransaction(
                txid, verbose=verbose, _res=responses, _exclude_services=_exclude_services, _r=_r+1
            )
        assert transaction['rawtx']
        return transaction

    async def gettxout(self, txid: str, index: int):
        return await self._gettxout(txid, index)

    @staticmethod
    def _join_txout(responses: typing.List):
        count_unspent_vote = []
        filtered_responses = []
        for r in responses:
            if r['in_block'] is None:
                if r['unspent'] is not None:
                    count_unspent_vote.append(r['unspent'])
            else:
                filtered_responses.append(r)
        responses = filtered_responses
        for x in [
            'value_satoshi', 'script_hex', 'script_type', 'unspent', 'in_block'
        ]:
            try:
                evaluation = [
                    r[x] for r in responses if r[x] not in ([], None)
                ] + count_unspent_vote if x == 'unspent' else []
                assert len(set(evaluation)) <= 1, evaluation
            except AssertionError:
                Logger.third_party.exception('Quorum on join tx out')
                return
        return responses and {
            "in_block": responses[0]['in_block'],
            "in_block_height": None,
            "value_satoshi": responses[0]['value_satoshi'],
            "script_hex": responses[0]['script_hex'],
            "script_asm": random.choice([r['script_asm'] for r in responses if r] or [None]),  # FIXME - TODO - quorum
            "script_type": responses[0]['script_type'],
            "addresses": random.choice([r['addresses'] for r in responses if r] or [None]),  # FIXME - TODO - quorum
            "unspent": responses[0]['unspent'],
        } or {}

    @staticmethod
    def _is_txout_complete(txout: typing.Dict):
        is_complete = [txout[v] for v in txout if v not in ['in_block_height', 'script_asm']]
        evaluation = txout and all(is_complete) or False
        return evaluation

    async def _gettxout(self, txid: str, index: int, _res=None, _exclude_services=None, _r=0):
        if _r > 5:
            return {}
        _exclude_services = _exclude_services or []
        services = self._pick_sources(_exclude_services)

        responses = _res or []
        futures = [service.gettxout(txid, index) for service in services]
        for response in await asyncio.gather(*futures):
            response and responses.append(response)
        if not responses:
            _exclude_services.extend(services)
            return await self._gettxout(txid, index, _res=responses, _exclude_services=services, _r=_r+1)
        txout = self._join_txout(responses)
        if not self._is_txout_complete(txout):
            _exclude_services.extend(services)
            return await self._gettxout(txid, index, _res=responses, _exclude_services=services, _r=_r+1)
        return txout

    async def getbestblockhash(self):
        res = await self.electrod.getbestblockhash()
        return res and res

    async def getblockhash(self, blockheight: int):
        return await self.electrod.getblockhash(blockheight)

    async def getblockheader(self, blockhash: str):
        return await self.electrod.getblockheader(blockhash)

    async def getblockcount(self):
        return await self.electrod.getblockcount()

    async def estimatefee(self, blocks: int):
        return await self.electrod.estimatefee(blocks)

    async def getbestblockheader(self):
        return await self.electrod.getbestblockheader()
