import binascii
from typing import Dict, List
from pycoin.tx.Tx import Tx
from spruned.application.database import ldb_batch
from spruned.application.logging_factory import Logger
from spruned.application.tools import deserialize_header

TRANSACTION_PREFIX = b'\x00'
BLOCK_PREFIX = b'\x01'


class BlockchainRepository:
    def __init__(self, session, storage_name, dbpath):
        self.storage_name = storage_name
        self.session = session
        self.dbpath = dbpath
        self._cache = None
        self.volatile = {}

    def save_json_transaction(self, txid: str, txdict: dict):
        # todo, at least avoid during same session
        self.volatile[txid] = txdict

    def get_json_transaction(self, txid: dict):
        # todo
        return self.volatile.get(txid)

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
        key = self.get_key(block['block_hash'], prefix=BLOCK_PREFIX)
        self.session.put(self.storage_name + b'.' + key, block['block_bytes'])
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

    def is_block_saved(self, blockhash: str) -> bool:
        key = self.get_key(blockhash, prefix=BLOCK_PREFIX)
        data = self.session.get(self.storage_name + b'.' + key)
        return bool(data)

    def get_block(self, blockhash: str) -> (None, Dict):
        key = self.get_key(blockhash, prefix=BLOCK_PREFIX)
        data = self.session.get(self.storage_name + b'.' + key)
        if not data:
            Logger.leveldb.debug('%s not found under key %s', blockhash, key)
            return
        header = deserialize_header(data[:80])
        return {
            'block_hash': header['hash'],
            'block_bytes': data,
            'header_bytes': data[:80],
            'timestamp': header['timestamp']
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
        #if data:
        #    txids = utils.split(data[80:], offset=32)
        #    for txid in txids:
        #        self.remove_transaction(txid)
        #else:
        #    Logger.leveldb.warning('remove block on block not found: %s', blockhash)
        key = self.get_key(blockhash, prefix=BLOCK_PREFIX)
        self.session.delete(self.storage_name + b'.' + key)

    @ldb_batch
    def remove_transaction(self, txid: str):
        key = self.get_key(txid, prefix=TRANSACTION_PREFIX)
        self.session.delete(self.storage_name + b'.' + key)
