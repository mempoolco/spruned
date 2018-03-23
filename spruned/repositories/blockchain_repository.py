import io
import os
import binascii
import struct
import time
from typing import Dict, List
from leveldb import LevelDB
from pycoin.block import Block
from pycoin.tx.Tx import Tx
from spruned.application import utils
from spruned.application.database import ldb_batch
from spruned.application.logging_factory import Logger

TRANSACTION_PREFIX = b'\x00'
BLOCK_PREFIX = b'\x01'


class BlockchainRepository:
    """
    this special repository track what's in it, to ensure the size limit
    """
    def __init__(self, session, storage_name, dbpath, limit=None):
        self.storage_name = storage_name
        self.session: LevelDB = session
        self.limit = limit
        self.dbpath = dbpath
        self.limit and self._ensure_timestamps()

    def _deserialize_timestamp(self, blob: bytes):
        timestamp, key = struct.unpack('L', blob[:8]), blob[8:]
        return {'saved_at': timestamp, 'key': key}

    def _serialize_timestamp(self, data: Dict):
        d = struct.pack('L', data['saved_at'])
        d += data['key']
        return d

    def _get_key(self, name: str, prefix=b''):
        if isinstance(prefix, str):
            prefix = prefix.encode()
        if isinstance(name, str):
            name = binascii.unhexlify(name.encode())
        return self.storage_name + b'.' + (prefix and (prefix + b'.') or b'') + name

    def _ensure_timestamps(self):
        try:
            self.session.Get(self.storage_name + b'.timestamps')
        except KeyError:
            self.session.Put(self.storage_name + b'.timestamps', b'')

    @ldb_batch
    def track_put(self, key):
        data = self.session.Get(self.storage_name + b'.timestamps')
        track = {'key': key, 'saved_at': int(time.time())}
        data += self._serialize_timestamp(track)
        self.session.Put(self.storage_name + b'timestamps', data)
        return track

    @ldb_batch
    def get_timestamps(self):
        data = self.session.Get(self.storage_name + b'.timestamps')
        timestamps = [self._serialize_timestamp(chunk) for chunk in utils.split(data, 41)]
        return timestamps

    def _get_db_size(self):
        size = 0
        for file in os.listdir(self.dbpath):
            if 'ldb' in file:
                size += os.stat('database.ldb/' + file).st_size
        return size

    def purge(self):
        if not self.limit:
            raise ValueError('No limit set, cannot purge database')
        timestamps = self.get_timestamps()
        sorted_timestamps = sorted(timestamps, key=lambda x: x['saved_at'])
        while self._get_db_size() > self.limit:
            self.session.Delete(sorted_timestamps.pop()['key'])

    @ldb_batch
    def save_block(self, block: Dict) -> Dict:
        saved = self._save_block(block)
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
        key = self._get_key(_block.id(), prefix=BLOCK_PREFIX)
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
        self.session.Put(key, data)
        self.limit and self.track_put(key)
        return block

    @ldb_batch
    def save_transaction(self, transaction: Dict) -> Dict:
        blockhash = binascii.unhexlify(transaction['block_hash'].encode())
        data = transaction['transaction_bytes'] + blockhash
        key = self._get_key(transaction['txid'], prefix=TRANSACTION_PREFIX)
        self.session.Put(key, data)
        self.limit and self.track_put(key)
        return transaction

    @ldb_batch
    def save_transactions(self, *transactions: Dict) -> List[Dict]:
        saved = []
        for transaction in transactions:
            saved.append(self.save_transaction(transaction))
        return saved

    def get_block(self, blockhash: str) -> (None, Dict):
        key = self._get_key(blockhash, prefix=BLOCK_PREFIX)
        try:
            data = self.session.Get(key)
        except KeyError:
            Logger.leveldb.debug('%s not found under key %s', blockhash, key)
            return

        header = data[:80]
        txids = utils.split(data[80:], offset=32)
        block = Block.parse(io.BytesIO(header), include_transactions=False)
        transactions = [self.get_transaction(txid) for txid in txids]
        Logger.leveldb.debug('Found %s transactions for block %s', len(transactions), blockhash)
        block.set_txs([transaction['transaction_object'] for transaction in transactions])
        return {
            'block_hash': block.id(),
            'block_bytes': block.as_bin(),
            'header_bytes': header,
            'timestamp': block.timestamp,
            'block_object': block
        }

    def get_transaction(self, txid) -> (None, Dict):
        try:
            return self._get_transaction(txid)
        except KeyError:
            return None

    def _get_transaction(self, txid: (str, bytes)):
        key = self._get_key(txid, prefix=TRANSACTION_PREFIX)
        data = self.session.Get(key)
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
        self.session.Delete(self._get_key(blockhash, prefix=BLOCK_PREFIX))

    @ldb_batch
    def remove_transaction(self, txid: str):
        self.session.Delete(self._get_key(txid, prefix=TRANSACTION_PREFIX))
