import asyncio
import binascii
import itertools
import time
from spruned.application.cache import CacheAgent
from spruned.application.logging_factory import Logger
from spruned.application.tools import deserialize_header, script_to_scripthash, ElectrumMerkleVerify, is_address
from spruned.application import exceptions
from spruned.application.abstracts import RPCAPIService
from spruned.daemon.bitcoin_p2p.utils import get_block_factory
from spruned.daemon.exceptions import ElectrodMissingResponseException
from spruned.dependencies.pybitcointools import deserialize


class SprunedVOService(RPCAPIService):
    def __init__(self, electrod, p2p, cache: CacheAgent=None, repository=None,
                 loop=asyncio.get_event_loop(), context=None, fallback_non_segwit_blocks=False):
        self.cache = cache
        self.p2p = p2p
        self.electrod = electrod
        self.repository = repository
        self.loop = loop
        self._last_estimatefee = None
        self.block_factory = get_block_factory()
        self.context = context
        self._fallback_non_segwit_blocks = fallback_non_segwit_blocks
        self._expected_data = {'txids': []}

    def available(self):
        raise NotImplementedError

    async def get_block_object(self, blockhash: str):
        block_header = self.repository.headers.get_block_header(blockhash)
        if not block_header:
            return
        try:
            block = await self._get_block(block_header)
        except exceptions.ServiceException:
            if not self._fallback_non_segwit_blocks:
                raise
            block = await self._get_block(block_header, segwit=False)
        block_object = await self.block_factory.get(block['block_bytes'])
        return block_object

    async def getblock(self, blockhash: str, mode: int = 1):
        start = time.time()
        if mode == 2:
            raise NotImplementedError
        block_header = self.repository.headers.get_block_header(blockhash)
        if not block_header:
            return
        try:
            block = await self._get_block(block_header, verbose=mode == 1)
        except exceptions.ServiceException:
            if not self._fallback_non_segwit_blocks:
                raise
            block = await self._get_block(block_header, verbose=mode == 1, segwit=False)
        if mode == 1:
            if block.get('verbose'):
                res = block['verbose']
            else:
                res = self._make_verbose_block(block, block_header)
                self.loop.create_task(self.repository.blockchain.async_save_block(block, tracker=self.cache))
            best_header = self.repository.headers.get_best_header()
            res['confirmations'] = best_header['block_height'] - block_header['block_height'] + 1
        else:
            bb = block['block_bytes']
            res = binascii.hexlify(bb).decode()
        Logger.p2p.info(
            'Block {} ({}) provided in {:.4f}s)'.format(block_header['block_height'], blockhash, time.time() - start)
        )
        return res

    async def _make_verbose_block(self, block: dict, block_header) -> dict:
        block_object = await self.block_factory.get(block['block_bytes'])
        serialized = self._serialize_header(block_header or deserialize_header(block['block_bytes'][:80]))
        serialized['tx'] = [tx.id() for tx in block_object.txs]
        serialized['size'] = len(block['block_bytes'])
        return serialized

    async def _get_block(self, blockheader, retries=0, verbose=False, segwit=True):
        blockhash = blockheader['block_hash']
        storedblock = self.repository.blockchain.get_block(blockhash)
        block = storedblock or await self.p2p.get_block(blockhash, privileged_peers=retries > 3, segwit=segwit)
        if not block:
            if retries > 3:
                raise exceptions.ServiceException
            else:
                block = await self._get_block(blockheader, retries + 1, segwit=segwit)
        if verbose and not block.get('verbose'):
            block['verbose'] = await self._make_verbose_block(block, blockheader)
        if not storedblock:
            self.loop.create_task(self.repository.blockchain.async_save_block(block, tracker=self.cache))
        return block

    async def _get_electrum_transaction(self, txid: str, verbose=False, retries=0):
        try:
            response = await self.electrod.getrawtransaction(txid, verbose=verbose)
            if not response:
                raise exceptions.ItemNotFoundException
            if verbose:
                for vout in response.get('vout'):
                    if vout.get('value'):
                        vout['value'] = float(vout['value'])
            return response
        except:
            if txid not in self._expected_data['txids'] or retries > 10:
                raise
            await asyncio.sleep(1)
            return await self._get_electrum_transaction(txid, verbose=verbose, retries=retries + 1)

    async def getrawtransaction(self, txid: str, verbose=False):
        repo_tx = self.repository.blockchain.get_json_transaction(txid)
        transaction = repo_tx or await self._get_electrum_transaction(txid, verbose=True)
        block_header = None
        if not repo_tx and transaction.get('blockhash'):
            block_header = self.repository.headers.get_block_header(transaction['blockhash'])
            merkle_proof = await self.electrod.get_merkleproof(txid, block_header['block_height'])
            dh = deserialize_header(block_header['header_bytes'])
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

    async def sendrawtransaction(self, rawtx: str, allowhighfees=False):
        res = await self.electrod.sendrawtransaction(rawtx, allowhighfees=allowhighfees)
        try:
            binascii.unhexlify(res)
            self._expected_data['txids'].append(res)
            # This must be done to retry on race conditions in send\get rawtxs
            # And to avoid "local bias" (we can't simply store and return the local data)
        except:
            pass
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
            "versionHex": "",
            "merkleroot": _deserialized_header['merkle_root'],
            "time": _deserialized_header['timestamp'],
            "mediantime": _deserialized_header['timestamp'],
            "nonce": _deserialized_header['nonce'],
            "bits": str(_deserialized_header['bits']),
            "difficulty": 0,
            "chainwork": '00'*32,
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

    async def _estimatefee(self, blocks, retries=1):
        try:
            res = await self.electrod.estimatefee(blocks)
        except ElectrodMissingResponseException as e:
            Logger.electrum.error('Error with peer', exc_info=True)
            retries += 1
            if retries > 5:
                raise e
            return await self._estimatefee(blocks, retries + 1)
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
            "difficulty": 0,
            "chainwork": '00'*32,
            "mediantime": _deserialized_header["timestamp"],
            "verificationprogress": self.p2p.bootstrap_status,
            "pruned": False,

        }

    async def gettxout(self, txid: str, index: int):
        repo_tx = self.repository.blockchain.get_transaction(txid)
        transaction = repo_tx and binascii.hexlify(repo_tx['transaction_bytes']).decode() \
                        or await self._get_electrum_transaction(txid)
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
            "confirmations": best_header['block_height'] - txout['height'] + 1,
            "value": round(float(txout['value'] / 10**8), 8),
            "scriptPubKey": {
                "asm": "",  # todo
                "hex": deserialized_vout['script'],
                "reqSigs": 0,  # todo
                "type": "",
                "addresses": []  # todo
            }
        }

    async def _listunspent_by_scripthash(self, scripthash, retries=0):
        try:
            unspents = await self.electrod.listunspents_by_scripthash(scripthash)
        except:
            if retries > 15:
                return
            return await self._listunspent_by_scripthash(scripthash, retries=retries+1)
        return unspents

    async def getpeerinfo(self):
        electrum_peers = self.electrod.get_peers()
        p2p_peers = self.p2p.get_peers()
        response = []
        for peer in itertools.chain(electrum_peers, p2p_peers):
            response.append(
                {
                    "addr": "{}:{}".format(peer.hostname, peer.port),
                    "subver": peer.subversion,
                    "conntime": peer.connected_at,
                    "startingheight": peer.starting_height and int(peer.starting_height)
                }
            )
        return response

    async def getmempoolinfo(self):
        if not self.repository.mempool:
            raise exceptions.MempoolDisabledException
        return self.repository.mempool.get_mempool_info()

    async def getrawmempool(self, verbose):
        if not self.repository.mempool:
            raise exceptions.MempoolDisabledException
        mempool_txids = self.repository.mempool.get_raw_mempool(verbose)
        return mempool_txids

    async def validateaddress(self, address):
        return bool(is_address(address, self.context.get_network()['regex_legacy_addresses_prefix']))
