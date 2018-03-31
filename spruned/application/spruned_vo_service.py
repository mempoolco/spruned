import hashlib
import random
import binascii

from bitcoin import deserialize
from pycoin.tx import TxOut
from pycoin.tx.Tx import Tx

from spruned import settings
from spruned.application.cache import CacheAgent
from spruned.application.database import ldb_batch
from spruned.application.logging_factory import Logger
from spruned.application.tools import deserialize_header, script_to_scripthash
from spruned.application import exceptions
from spruned.application.abstracts import RPCAPIService
from spruned.daemon.exceptions import ElectrodMissingResponseException


class SprunedVOService(RPCAPIService):
    def __init__(self, electrod, p2p, cache: CacheAgent=None, utxo_tracker=None, repository=None):
        self.sources = []
        self.primary = []
        self.cache = cache
        self.p2p = p2p
        self.electrod = electrod
        self.min_sources = 1
        self.current_best_height = None
        self.utxo_tracker = utxo_tracker
        self.repository = repository

    def available(self):
        raise NotImplementedError

    async def getblock(self, blockhash: str, mode: int=1):
        block_header = self.repository.headers.get_block_header(blockhash)
        if not block_header:
            return
        block = await self._get_block(block_header)
        if mode == 1:
            best_header = self.repository.headers.get_best_header()
            block['confirmations'] = best_header['block_height'] - block_header['block_height']
            serialized = self._serialize_header(block_header)
            serialized['tx'] = [tx.id() for tx in block['block_object'].txs]
            return serialized
        elif mode == 2:
            raise NotImplementedError
        return binascii.hexlify(block['block_bytes']).decode()

    @ldb_batch
    async def _get_block(self, blockheader, _r=0):
        blockhash = blockheader['block_hash']
        storedblock = self.repository.blockchain.get_block(blockhash)
        block = storedblock or await self.p2p.get_block(blockhash, timeout=10)
        if not block:
            if _r > 10:
                raise exceptions.ServiceException
            else:
                return await self._get_block(blockheader, _r + 1)
        if not storedblock:
            self.repository.blockchain.save_block(block, tracker=self.cache)
        return block

    async def getrawtransaction(self, txid: str, verbose=False):
        repo_tx = self.repository.blockchain.get_transaction(txid)
        transaction = repo_tx or await self.electrod.getrawtransaction(txid)
        res = {
            'source': 'p2p' if repo_tx else 'electrum',
            'rawtx': binascii.hexlify(repo_tx['transaction_object'].as_bin()).decode() if repo_tx else transaction
        }
        if verbose:
            return res
        return res['rawtx']

    async def getbestblockhash(self):
        res = self.repository.headers.get_best_header().get('block_hash')
        return res and res

    async def getblockhash(self, blockheight: int):
        return self.repository.headers.get_block_hash(blockheight)

    async def getblockheader(self, blockhash: str, verbose=True):
        header = self.repository.headers.get_block_header(blockhash)
        if verbose:
            _best_header = self.repository.headers.get_best_header()
            res = self._serialize_header(header)
            res["confirmations"] = _best_header['block_height'] - header['block_height'] + 1
        else:
            res = binascii.hexlify(header['header_bytes']).decode()
        return res

    @staticmethod
    def _serialize_header(header):
        _deserialized_header = deserialize_header(binascii.hexlify(header['header_bytes']).decode())
        return {
            "hash": _deserialized_header['hash'],
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

    async def getblockcount(self):
        return self.repository.headers.get_best_header().get('block_height')

    async def estimatefee(self, blocks: int):
        return await self._estimatefee(blocks)

    async def _estimatefee(self, blocks, _r=1):
        try:
            res = await self.electrod.estimatefee(blocks)
        except ElectrodMissingResponseException as e:
            Logger.electrum.error('Error with peer', exc_info=True)
            _r += 1
            if _r > 5:
                raise e
            return await self._estimatefee(blocks, _r + 1)
        return res

    async def getbestblockheader(self, verbose=True):
        best_header = self.repository.headers.get_best_header()
        return await self.getblockheader(best_header['block_hash'], verbose=verbose)

    async def getblockchaininfo(self):
        best_header = self.repository.headers.get_best_header()
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
            "verificationprogress": self.p2p.bootstrap_status,
            "pruned": False,
        }

    async def gettxout(self, txid: str, index: int):
        repo_tx = self.repository.blockchain.get_transaction(txid)
        transaction = repo_tx and binascii.hexlify(repo_tx['transaction_bytes']) \
                        or await self.electrod.getrawtransaction(txid)
        deserialized = deserialize(transaction)
        vout = deserialized['outs'][index]
        scripthash = script_to_scripthash(vout['script'])
        unspents = await self._listunspent_by_scripthash(scripthash) or []
        txout = None
        for unspent in unspents:
            if unspent['tx_hash'] == txid and unspent['tx_pos'] == index:
                txout = unspent
        return txout and await self._format_gettxout(txout, vout)

    async def _format_gettxout(self, txout: dict, deserialized_vout: dict):
        best_header = self.repository.headers.get_best_header()
        return {
            "bestblock": best_header['block_hash'],
            "confirmations": best_header['block_height'] - txout['height'],
            "value": round(txout['value'] / 10**8, 8),
            "scriptPubKey": {
                "asm": None,  # todo
                "hex": deserialized_vout['script'],
                "reqSigs": None,  # todo
                "type": "",
                "addresses": []  # todo
            }
        }

    async def _listunspent_by_scripthash(self, scripthash, _r=0):
        try:
            unspents = await self.electrod.listunspents_by_scripthash(scripthash)
        except:
            if _r > 15:
                return
            return await self._listunspent_by_scripthash(scripthash, _r=_r+1)
        return unspents


