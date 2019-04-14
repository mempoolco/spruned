import binascii
from typing import Dict, List

from pycoin.block import Block

from spruned.application.database import ldb_batch
from spruned.application.logging_factory import Logger
from spruned.repositories.abstracts import BlockchainRepositoryAbstract

TRANSACTION_PREFIX = b'\x00'
BLOCK_INDEX_PREFIX = b'\x02'
DB_VERSION = b'\x04'


class BlockchainRepository(BlockchainRepositoryAbstract):
    current_version = 2

    def __init__(self, session, storage_name, dbpath):
        self.storage_name = storage_name
        self.session = session
        self.dbpath = dbpath
        self._cache = None
        self.volatile = {}

    def erase(self):
        from spruned.application.database import init_ldb_storage, erase_ldb_storage
        self.session.close()
        erase_ldb_storage()
        self.session = init_ldb_storage()
        self.save_db_version()

    def save_db_version(self):
        self.session.put(self.storage_name + b'.' + DB_VERSION, self.current_version.to_bytes(8, 'little'))

    def get_db_version(self):
        v = self.session.get(self.storage_name + b'.' + DB_VERSION)
        return v and int.from_bytes(v, 'little')

    def set_cache(self, cache):
        self._cache = cache

    def get_key(self, name: (bytes, str), prefix=b''):
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
        block['size'] = len(block['block_bytes'])
        block['block_object'] = block.get('block_object', Block.from_bin(block.get('block_bytes')))

        blockhash = binascii.unhexlify(block['block_hash'].encode())
        txids = list()
        for transaction in block['block_object'].txs:
            self.save_transaction({
                'txid': transaction.id(),
                'transaction_bytes': transaction.as_bin(),
                'block_hash': blockhash
            })
            txids.append(binascii.unhexlify(transaction.id()))
        self._save_block_index(blockhash, block['size'], txids)
        tracker and tracker.track(
            self.get_key(block['block_hash'], prefix=BLOCK_INDEX_PREFIX),
            len(block['block_bytes'])
        )
        return block

    @ldb_batch
    def _save_block_index(self, blockhash: bytes, blocksize: int, txids: List[bytes]):
        key = self.get_key(blockhash, prefix=BLOCK_INDEX_PREFIX)
        size = blocksize.to_bytes(4, 'little')
        self.session.put(self.storage_name + b'.' + key, size + b''.join(txids))

    def get_block_index(self, blockhash: str):
        key = self.get_key(blockhash, prefix=BLOCK_INDEX_PREFIX)
        return self.session.get(self.storage_name + b'.' + key)

    @ldb_batch
    def save_blocks(self, *blocks: Dict) -> List[Dict]:
        saved = []
        for block in blocks:
            saved.append(self.save_block(block))
        return saved

    @ldb_batch
    def save_transaction(self, transaction: Dict) -> Dict:
        data = transaction['transaction_bytes'] + transaction['block_hash']
        key = self.get_key(transaction['txid'], prefix=TRANSACTION_PREFIX)
        self.session.put(self.storage_name + b'.' + key, data)
        return transaction

    def get_txids_by_block_hash(self, blockhash: str) -> (List[str], int):
        block_index = self.get_block_index(blockhash)
        if not block_index:
            return [], None
        i = 0
        txids = []
        size = block_index[:4]
        block_index = block_index[4:]
        while 1:
            txid = binascii.hexlify(block_index[i:i + 32]).decode()
            if not txid:
                break
            txids.append(txid)
            i += 32
        return txids, int.from_bytes(size, 'little')

    def get_transactions_by_block_hash(self, blockhash: str) -> (List[Dict], int):
        block_index = self.get_block_index(blockhash)
        if not block_index:
            return [], None
        i = 0
        size = block_index[:4]
        block_index = block_index[4:]
        transactions = []
        while 1:
            txid = block_index[i:i+32]
            if not txid:
                break
            transaction = self.get_transaction(txid)
            if not transaction:
                if transactions:
                    Logger.repository.warning('Corrupted storage for blockhash %s, deleting' % blockhash)
                    self.remove_block(blockhash)
                    return [], None
                break
            transactions.append(transaction)
            i += 32
        return transactions, int.from_bytes(size, 'little')

    def get_transaction(self, txid: (bytes, str)) -> (None, Dict):
        key = self.get_key(txid, prefix=TRANSACTION_PREFIX)
        data = self.session.get(self.storage_name + b'.' + key)
        if not data:
            return
        return {
            'transaction_bytes': data[:-32],
            'block_hash': data[-32:],
            'txid': txid
        }

    @ldb_batch
    def remove_block(self, blockhash: str):
        txids, size = self.get_txids_by_block_hash(blockhash)
        for txid in txids:
            key = self.get_key(txid, prefix=TRANSACTION_PREFIX)
            self._remove_item(key)
        self._remove_item(self.get_key(blockhash, prefix=BLOCK_INDEX_PREFIX))

    @ldb_batch
    def _remove_item(self, key):
        self.session.delete(self.storage_name + b'.' + key)
