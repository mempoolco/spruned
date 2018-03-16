import json
import typing
import random
import binascii
import asyncio
from spruned.application.tools import deserialize_header
from spruned.application import settings, exceptions
from spruned.application.abstracts import RPCAPIService, StorageInterface
from spruned.application.cache import cache_block, cache_transaction
from spruned.application.logging_factory import Logger


class SprunedVOService(RPCAPIService):
    def __init__(self, electrod, cache=None, utxo_tracker=None, repository=None):
        self.sources = []
        self.primary = []
        self.cache = cache
        self.electrod = electrod
        self.min_sources = 1
        self.current_best_height = None
        self.utxo_tracker = utxo_tracker
        self.repository = repository

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
        repo_header = self.repository.get_block_header(block['hash'])
        _header = binascii.hexlify(repo_header['data']).decode()
        header = deserialize_header(_header)
        block['version'] = header['version']
        block['time'] = header['timestamp']
        block['versionHex'] = None
        block['mediantime'] = None
        block['nonce'] = header['nonce']
        block['bits'] = header['bits']
        block['difficulty'] = None
        block['chainwork'] = None
        block['previousblockhash'] = header['prev_block_hash']
        block['height'] = repo_header['block_height']
        # TODO Verify transactions tree
        if header.get('nextblockhash'):
            block['nextblockhash'] = repo_header.get('next_block_hash')
        block.pop('confirmations', None)
        return block

    async def _getblock(self, blockhash: str, _res=None, _exclude_services=None, _r=0):
        if _r > 5:
            return
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
            return
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
                transaction['rawtx'] = electrod_transaction
                transaction['source'] += ', electrum'
        if not self._is_complete(transaction):
            _exclude_services.extend(services)
            return await self._getrawtransaction(
                txid, verbose=verbose, _res=responses, _exclude_services=_exclude_services, _r=_r+1
            )
        assert transaction['rawtx']
        return transaction

    async def gettxout(self, txid: str, index: int):
        response = await self._gettxout(txid, index)
        if not response:
            return
        best_block_header = self.repository.get_best_header()
        tx_blockheader = self.repository.get_block_header(response['in_block'])
        in_block_height = tx_blockheader['block_height']
        confirmations = best_block_header['block_height'] - in_block_height
        return {
            "bestblock": best_block_header['block_hash'],
            "confirmations": confirmations,
            "value": '{:.8f}'.format(response['value_satoshi'] / 10**8),
            "scriptPubKey": {
                "asm": response['script_asm'],
                "hex": response['script_hex'],
                "reqSigs": "Not Implemented Yet",
                "type": response["script_type"],
                "addresses": response["addresses"]
            },
            "coinbase": "Not Implemented Yet"
        }


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
                ] + (count_unspent_vote if x == 'unspent' else [])
                assert len(set(evaluation)) <= 1
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
        }

    @staticmethod
    def _is_txout_complete(txout: typing.Dict):
        res = txout and all([txout[v] for v in txout if v not in ['in_block_height', 'script_asm', 'unspent']])
        return res and txout['unspent'] is not None

    async def _gettxout(self, txid: str, index: int, _res=None, _exclude_services=None, _r=0):
        if _r > 5:
            return
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
        try:
            if not await self.ensure_unspent_consistency_with_electrum_network(txid, index, txout):
                return await self._gettxout(txid, index, _res=responses, _exclude_services=services, _r=_r + 1)
        except exceptions.SpentTxOutException:
            Logger.electrum.exception("Can't find a solution for gettxout between electrum and local services")
            return
        return txout

    async def ensure_unspent_consistency_with_electrum_network(self, txid: str, index: int, data: typing.Dict):
        if not data['addresses']:
            if settings.ALLOW_UNSAFE_UTXO:
                return True
            return
        if data['script_type'] == 'nulldata':  # I'm not sure if nulldata can reach this point, investigate.
            return True
        found = False
        unspents = await self.electrod.listunspents(data['addresses'][0])
        if not unspents:
            return
        for unspent in unspents:
            if unspent['tx_hash'] == txid and unspent['tx_pos'] == index:
                found = unspent
                break
        if not data['unspent'] and found:
            Logger.third_party.debug('unspent not found in the electrum listunspent for the given address')
            self.utxo_tracker and not data['unspent'] and self.utxo_tracker.invalidate_spent(txid, index)
            raise exceptions.SpentTxOutException

        if data['unspent'] and not found:
            if bool(data['value_satoshi'] != found['value']):
                raise exceptions.SpentTxOutException
        return True

    async def getbestblockhash(self):
        res = self.repository.get_best_header().get('block_hash')
        return res and res

    async def getblockhash(self, blockheight: int):
        return self.repository.get_block_hash(blockheight)

    async def getblockheader(self, blockhash: str, verbose=True):
        header = self.repository.get_block_header(blockhash)
        if verbose:
            _best_header = self.repository.get_best_header()
            _deserialized_header = deserialize_header(binascii.hexlify(header['data']).decode())
            res = {
                  "hash": _deserialized_header['hash'],
                  "confirmations": _best_header['block_height'] - header['block_height'] + 1,
                  "height": header['block_height'],
                  "version": _deserialized_header['version'],
                  "versionHex": "Not Implemented Yet",
                  "merkleroot": _deserialized_header['merkle_root'],
                  "time": _deserialized_header['timestamp'],
                  "mediantime": _deserialized_header['timestamp'],
                  "nonce": _deserialized_header['nonce'],
                  "bits": _deserialized_header['bits'],
                  "difficulty": "Not Implemented Yet",
                  "chainwork": "Not Implemented Yet",
                  "previousblockhash": _deserialized_header['prev_block_hash'],
                  "nextblockhash": header.get('next_block_hash')
                }
        else:
            res = binascii.hexlify(header['data']).decode()
        return res

    async def getblockcount(self):
        return self.repository.get_best_header().get('block_height')

    async def estimatefee(self, blocks: int):
        return await self.electrod.estimatefee(blocks)

    async def getbestblockheader(self, verbose=True):
        best_header = self.repository.get_best_header()
        return self.getblockheader(best_header['block_hash'], verbose=verbose)

    async def getblockchaininfo(self):
        best_header = self.repository.get_best_header()
        _deserialized_header = deserialize_header(best_header['data'])
        return {
            "chain": "main",
            "warning": "spruned v%s. emulating bitcoind v%s" % (settings.VERSION, settings.BITCOIND_API_VERSION),
            "blocks": best_header["block_height"],
            "headers": best_header["block_height"],
            "bestblockhash": best_header["block_hash"],
            "difficulty": None,
            "chainwork": None,
            "mediantime": _deserialized_header["timestamp"],
            "verificationprogress": 0,
            "pruned": False,
        }
