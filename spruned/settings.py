from enum import Enum
import os
from pathlib import Path


class Network(Enum):
    BITCOIN = 1
    BITCOIN_TESTNET = 2


# application
DEBUG = True
TESTNET = 0
CACHE = 1024
NETWORK = Network.BITCOIN
SPRUNED_SERVICE_URL = 'https://spruned.mempool.co/data/'
MIN_DATA_SOURCES = 1


# secrets
BITCOIND_URL = os.getenv('BITCOIND_URL').encode()
BITCOIND_USER = os.getenv('BITCOIND_USER').encode()
BITCOIND_PASS = os.getenv('BITCOIND_PASS').encode()
BLOCKTRAIL_API_KEY = os.getenv('BLOCKTRAIL_API_KEY')
BLOCKCYPHER_API_TOKEN = os.getenv('BLOCKCYPHER_API_TOKEN')


# files
FILE_DIRECTORY = '%s/.spruned' % Path.home()
CACHE_ADDRESS = '%s/cache/' % FILE_DIRECTORY
STORAGE_ADDRESS = '%s/storage/' % FILE_DIRECTORY
LOGFILE = '%s/spruned.log' % FILE_DIRECTORY


# electrum
ENABLE_ELECTRUM = True
ELECTRUM_CONCURRENCY = 3
