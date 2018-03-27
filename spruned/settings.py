from enum import Enum
import os
from pathlib import Path


TESTING = os.getenv('TESTING')

class Network(Enum):
    BITCOIN = 1
    BITCOIN_TESTNET = 2

# bitcoin
# https://github.com/bitcoin/bitcoin/blob/master/src/chainparams.cpp
CHECKPOINTS = {
    0: "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
    11111: "0000000069e244f73d78e8fd29ba2fd2ed618bd6fa2ee92559f542fdb26e7c1d",
    33333: "000000002dd5588a74784eaa7ab0507a18ad16a236e7b1ce69f00d7ddfb5d0a6",
    74000: "0000000000573993a3c9e41ce34471c079dcf5f52a0e824a81e7f953b8661a20",
    105000: "00000000000291ce28027faea320c8d2b054b2e0fe44a773f3eefb151d6bdc97",
    134444: "00000000000005b12ffd4cd315cd34ffd4a594f430ac814c91184a0d42d2b0fe",
    168000: "000000000000099e61ea72015e79632f216fe6cb33d7899acb35b75c8303b763",
    193000: "000000000000059f452a5f7340de6682a977387c17010ff6e6c3bd83ca8b1317",
    210000: "000000000000048b95347e83192f69cf0366076336c639f9b7228e9ba171342e",
    216116: "00000000000001b4f4b433e81ee46494af945cf96014816a4e2370f11b23df4e",
    225430: "00000000000001c108384350f74090433e7fcf79a606b8e797f065b130575932",
    250000: "000000000000003887df1f29024b06fc2200b55f8af8f35453d7be294df2d214",
    279000: "0000000000000001ae8c72a0b0c301f67e3afca10e819efa9041e458e9bd7e40",
    295000: "00000000000000004d9b4ef50f0f9d686fd69db2e03af35a100370c64632a983",
    418824: "0000000000000000001c8018d9cb3b742ef25114f27563e3fc4a1902167f9893",
    478559: "00000000000000000019f112ec0a9982926f1258cdcc558dd7c3b7e5dc7fa148"
}

# application
DEBUG = True
TESTNET = 0
CACHE_SIZE = 1024 * 1024 * 50
NETWORK = Network.BITCOIN
SPRUNED_SERVICE_URL = 'https://spruned.mempool.co/data/'
MIN_DATA_SOURCES = 1
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
    'm.root-servers.net',
    'www.bitcoin.org'
]

# third-party secrets
BLOCKTRAIL_API_KEY = os.getenv('BLOCKTRAIL_API_KEY')
BLOCKCYPHER_API_TOKEN = os.getenv('BLOCKCYPHER_API_TOKEN')

# files
SQLITE_DBNAME = ''
LEVELDB_BLOCKCHAIN_ADDRESS = ''

if not TESTING:
    FILE_DIRECTORY = '%s/.spruned' % Path.home()
    STORAGE_ADDRESS = '%s/storage/' % FILE_DIRECTORY
    LOGFILE = '%s/spruned.log' % FILE_DIRECTORY
    SQLITE_DBNAME = '%sheaders.db' % STORAGE_ADDRESS
    LEVELDB_BLOCKCHAIN_ADDRESS = '%sdatabase.ldb' % STORAGE_ADDRESS


LEVELDB_BLOCKCHAIN_SLUG = b'blockchain'
LEVELDB_CACHE_SLUG = b'cache'

# electrod
ELECTROD_CONNECTIONS = 3

JSONRPCSERVER_HOST = 'localhost'
JSONRPCSERVER_PORT = '8332'
JSONRPCSERVER_USER = 'rpcuser'
JSONRPCSERVER_PASSWORD = 'rpcpassword'

ALLOW_UNSAFE_UTXO = True

VERSION = "0.0.1"
BITCOIND_API_VERSION = "0.16"
BOOTSTRAP_BLOCKS = 50
