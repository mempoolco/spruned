import os
import binascii
from spruned.application.context import ctx

TESTING = os.getenv('TESTING')
CHECK_NETWORK_HOST = [
    'a.root-servers.net',
    'b.root-servers.net',
    'c.root-servers.net',
    'd.root-servers.net',
    'e.root-servers.net',
    'f.root-servers.net',
    'g.root-servers.net',
    'h.root-servers.net',
    'i.root-servers.net',
    'j.root-servers.net',
    'k.root-servers.net',
    'l.root-servers.net',
    'm.root-servers.net'
]
LEVELDB_INDEX_PATH = '/tmp/%s-test.index' % binascii.hexlify(os.urandom(8))
BLOCKS_PATH = '/tmp/%s-test.blocks' % binascii.hexlify(os.urandom(8))

if not TESTING:
    STORAGE_ADDRESS = '%s/storage/' % ctx.datadir
    LOGFILE = '%s/spruned.log' % ctx.datadir
    LEVELDB_INDEX_PATH = '%sblockchain/index' % STORAGE_ADDRESS
    BLOCKS_PATH = '%sblockchain/blocks' % STORAGE_ADDRESS
    UTXO_INDEX_PATH = '%sutxo/index' % STORAGE_ADDRESS
    UTXO_REV_STATE_PATH = '%sutxo/revstate' % STORAGE_ADDRESS
    for directory in (
        STORAGE_ADDRESS,
        LEVELDB_INDEX_PATH,
        BLOCKS_PATH,
        UTXO_REV_STATE_PATH,
        UTXO_INDEX_PATH,
    ):
        os.makedirs(directory, exist_ok=True)
