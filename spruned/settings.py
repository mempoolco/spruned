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
SQLITE_DBNAME = ''
LEVELDB_BLOCKCHAIN_ADDRESS = '/tmp/%s-test.ldb' % binascii.hexlify(os.urandom(8))
LEVELDB_BLOCKCHAIN_SLUG = b'b'
LEVELDB_CACHE_SLUG = b'c'

if not TESTING:
    STORAGE_ADDRESS = '%s/storage/' % ctx.datadir
    LOGFILE = '%s/spruned.log' % ctx.datadir
    SQLITE_DBNAME = '%sheaders.db' % STORAGE_ADDRESS
    LEVELDB_BLOCKCHAIN_ADDRESS = '%sdatabase.ldb' % STORAGE_ADDRESS
