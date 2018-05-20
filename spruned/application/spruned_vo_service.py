import asyncio
import io
import binascii
from pycoin.block import Block
from spruned.application.cache import CacheAgent
from spruned.application.logging_factory import Logger
from spruned.application.tools import deserialize_header, script_to_scripthash, ElectrumMerkleVerify
from spruned.application import exceptions
from spruned.application.abstracts import RPCAPIService
from spruned.daemon.exceptions import ElectrodMissingResponseException
from spruned.dependencies.pybitcointools import deserialize


class SprunedVOService(RPCAPIService):
    def __init__(self, electrod, p2p, cache: CacheAgent=None, repository=None,
                 loop=asyncio.get_event_loop()):
        self.cache = cache
        self.p2p = p2p
        self.electrod = electrod
        self.repository = repository
        self.loop = loop
        self._last_estimatefee = None

    def available(self):
        raise NotImplementedError

    async def getblock(self, blockhash: str, mode: int=1):
        if mode == 2:
            raise NotImplementedError
        block_header = self.repository.headers.get_block_header(blockhash)
        if not block_header:
            return
        block = await self._get_block(block_header)
        if mode == 1:
            block_object = block.get('block_object', Block.parse(io.BytesIO(block['block_bytes'])))
            best_header = self.repository.headers.get_best_header()
            block['confirmations'] = best_header['block_height'] - block_header['block_height']
            serialized = self._serialize_header(block_header)
            serialized['tx'] = [tx.id() for tx in block_object.txs]
            del block
            return serialized
        bb = block['block_bytes']
        del block
        return binascii.hexlify(bb).decode()

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
            self.loop.create_task(self.repository.blockchain.async_save_block(block, tracker=self.cache))
        return block

    async def getrawtransaction(self, txid: str, verbose=False):
        repo_tx = self.repository.blockchain.get_json_transaction(txid)
        transaction = repo_tx or await self.electrod.getrawtransaction(txid, verbose=True)
        block_header = None
        if not repo_tx and transaction.get('blockhash'):
            block_header = self.repository.headers.get_block_header(transaction['blockhash'])
            merkle_proof = await self.electrod.get_merkleproof(txid, block_header['block_height'])
            dh = deserialize_header(block_header['header_bytes'])
            dh['merkle_root'] = binascii.hexlify(dh['merkle_root'])
            if not ElectrumMerkleVerify.verify_merkle(txid, merkle_proof, dh):
                raise exceptions.InvalidPOWException
            if transaction.get('confirmations') > 2:
                self.repository.blockchain.save_json_transaction(txid, transaction)
        if verbose:
            if transaction.get('blockhash'):
                incl_height = block_header and block_header['block_height'] or \
                  self.repository.headers.get_block_header(transaction['blockhash'])['block_height']
                transaction['confirmations'] = ((await self.getblockcount()) - incl_height) + 1
            return transaction
        return transaction['hex']

    async def getbestblockhash(self):
        res = self.repository.headers.get_best_header().get('block_hash')
        return res and res

    async def sendrawtransaction(self, rawtx: str):
        res = await self.electrod.sendrawtransaction(rawtx)
        return res

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

    async def getblockcount(self) -> int:
        return self.repository.headers.get_best_header().get('block_height')

    async def estimatefee(self, blocks: int):
        try:
            self._last_estimatefee = await self._estimatefee(blocks)
        except:
            pass
        return self._last_estimatefee

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
        from spruned import __version__ as spruned_version
        from spruned import __bitcoind_version_emulation__ as bitcoind_version
        best_header = self.repository.headers.get_best_header()
        _deserialized_header = deserialize_header(best_header['header_bytes'])
        return {
            "chain": "main",
            "warning": "spruned %s, emulating bitcoind v%s" % (spruned_version, bitcoind_version),
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
        transaction = repo_tx and binascii.hexlify(repo_tx['transaction_bytes']).decode() \
                        or await self.electrod.getrawtransaction(txid)
        if not transaction:
            return
        deserialized = deserialize(transaction)
        if index + 1 > len(deserialized['outs']):
            return
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
            "value": "{:.8f}".format(txout['value'] / 10**8, 8),
            "scriptPubKey": {
                "asm": "",  # todo
                "hex": deserialized_vout['script'],
                "reqSigs": 0,  # todo
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
