import io
import binascii
import time
from typing import Dict, List
from pycoin.block import Block
from pycoin.tx.Tx import Tx
from spruned.application import utils, exceptions
from spruned.application.database import ldb_batch
from spruned.application.logging_factory import Logger

TRANSACTION_PREFIX = b'\x00'
BLOCK_PREFIX = b'\x01'


class BlockchainRepository:
    def __init__(self, session, storage_name, dbpath):
        self.storage_name = storage_name
        self.session = session
        self.dbpath = dbpath
        self._cache = None

    def set_cache(self, cache):
        self._cache = cache

    def get_key(self, name: str, prefix=b''):
        if isinstance(prefix, str):
            prefix = prefix.encode()
        if isinstance(name, str):
            name = binascii.unhexlify(name.encode())
        return (prefix and (prefix + b'.') or b'') + name

    async def async_save_block(self, block: Dict, tracker=None, callback=None):
        res = self.save_block(block, tracker)
        callback and callback(res)

    @ldb_batch
    def save_block(self, block: Dict, tracker=None) -> Dict:
        saved = self._save_block(block)
        tracker and tracker.track(saved['key'], saved['size'])
        return saved

    @ldb_batch
    def save_blocks(self, *blocks: Dict) -> List[Dict]:
        saved = []
        for block in blocks:
            saved.append(self._save_block(block))
        return saved

    @ldb_batch
    def _save_block(self, block: Dict) -> Dict:
        _block = block['block_object']
        key = self.get_key(_block.id(), prefix=BLOCK_PREFIX)
        data = bytes(_block.as_blockheader().as_bin())
        for tx in _block.txs:
            data += binascii.unhexlify(str(tx.id()))
            transaction = {
                'transaction_bytes': tx.as_bin(),
                'block_hash': _block.id(),
                'txid': tx.id()
            }
            self.save_transaction(transaction)
        assert len(data) % 32 == 16
        self.session.put(self.storage_name + b'.' + key, data)
        block['key'] = key
        block['size'] = len(block['block_bytes'])
        return block

    @ldb_batch
    def save_transaction(self, transaction: Dict) -> Dict:
        blockhash = binascii.unhexlify(transaction['block_hash'].encode())
        data = transaction['transaction_bytes'] + blockhash
        key = self.get_key(transaction['txid'], prefix=TRANSACTION_PREFIX)
        self.session.put(self.storage_name + b'.' + key, data)
        return transaction

    @ldb_batch
    def save_transactions(self, *transactions: Dict) -> List[Dict]:
        saved = []
        for transaction in transactions:
            saved.append(self.save_transaction(transaction))
        return saved

    def get_block(self, blockhash: str, with_transactions=True) -> (None, Dict):
        key = self.get_key(blockhash, prefix=BLOCK_PREFIX)
        now = time.time()
        data = self.session.get(self.storage_name + b'.' + key)
        if not data:
            Logger.leveldb.debug('%s not found under key %s', blockhash, key)
            return
        header = data[:80]
        block = Block.parse(io.BytesIO(header), include_transactions=False)
        if with_transactions:
            txids = utils.split(data[80:], offset=32)
            transactions = [self.get_transaction(txid) for txid in txids]
            if len(txids) != len(transactions):
                Logger.cache.error('Storage corrupted')
                return
            Logger.leveldb.debug('Found %s transactions for block %s', len(transactions), blockhash)
            block.set_txs([transaction['transaction_object'] for transaction in transactions])
            Logger.leveldb.debug('Blockchain storage, transaction mounted in {:.4f}'.format(time.time() - now))
        return {
            'block_hash': block.id(),
            'block_bytes': block.as_bin(),
            'header_bytes': header,
            'timestamp': block.timestamp,
            'block_object': block
        }

    def get_transaction(self, txid) -> (None, Dict):
        return self._get_transaction(txid)

    def _get_transaction(self, txid: (str, bytes)):
        key = self.get_key(txid, prefix=TRANSACTION_PREFIX)
        data = self.session.get(self.storage_name + b'.' + key)
        if not data:
            return
        blockhash = data[-32:]
        if not int.from_bytes(blockhash[:8], 'little'):
            data = data[:-32]
        return {
            'transaction_bytes': data,
            'block_hash': blockhash,
            'txid': txid,
            'transaction_object': Tx.from_bin(data)
        }

    @ldb_batch
    def remove_block(self, blockhash: str):
        key = self.get_key(blockhash, prefix=BLOCK_PREFIX)
        data = self.session.get(self.storage_name + b'.' + key)
        if data:
            txids = utils.split(data[80:], offset=32)
            for txid in txids:
                self.remove_transaction(txid)
        else:
            Logger.leveldb.warning('remove block on block not found: %s', blockhash)
        key = self.get_key(blockhash, prefix=BLOCK_PREFIX)
        self.session.delete(self.storage_name + b'.' + key)

    @ldb_batch
    def remove_transaction(self, txid: str):
        key = self.get_key(txid, prefix=TRANSACTION_PREFIX)
        self.session.delete(self.storage_name + b'.' + key)
