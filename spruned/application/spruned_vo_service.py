import typing
import random
import binascii
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

    @cache_block
    async def getblock(self, blockhash: str):
        source = random.choice(self.sources)
        block = await source.getblock(blockhash)
        await self._verify_block_with_local_header(block)
        return block

    async def _verify_block_with_local_header(self, block):
        repo_header = self.repository.get_block_header(block['hash'])
        _header = binascii.hexlify(repo_header['header_bytes']).decode()
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

    @cache_transaction
    async def getrawtransaction(self, txid: str, verbose=False):
        source = random.choice(self.sources)
        transaction = await source.getrawtransaction(txid, verbose)
        if not transaction:
            # design fixme
            return
        electrod_rawtx = await self.electrod.getrawtransaction(txid)
        transaction['rawtx'] = electrod_rawtx
        transaction['source'] += ', electrum'
        blockheader = self.repository.get_block_header(transaction['blockhash'])
        merkleproof = await self.electrod.getmerkleproof(txid, blockheader['block_height'])
        assert merkleproof  # todo verify
        return transaction

    async def gettxout(self, txid: str, index: int):
        source = random.choice(self.sources)
        txout = await source.gettxout(txid, index)
        if not txout:
            return
        if not await self.ensure_unspent_consistency_with_electrum_network(txid, index, txout):
            return

        best_block_header = self.repository.get_best_header()
        tx_blockheader = self.repository.get_block_header(txout['in_block'])
        in_block_height = tx_blockheader['block_height']
        confirmations = best_block_header['block_height'] - in_block_height
        return {
            "bestblock": best_block_header['block_hash'],
            "confirmations": confirmations,
            "value": '{:.8f}'.format(txout['value_satoshi'] / 10**8),
            "scriptPubKey": {
                "asm": txout['script_asm'],
                "hex": txout['script_hex'],
                "reqSigs": "Not Implemented Yet",
                "type": txout["script_type"],
                "addresses": txout["addresses"]
            },
            "coinbase": "Not Implemented Yet"
        }

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
            _deserialized_header = deserialize_header(binascii.hexlify(header['header_bytes']).decode())
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
            res = binascii.hexlify(header['header_bytes']).decode()
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
        _deserialized_header = deserialize_header(best_header['header_bytes'])
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
