from enum import Enum
import os


class Network(Enum):
    BITCOIN = 1
    BITCOIN_TESTNET = 2


TESTNET = 0
CACHE = 1024
NETWORK = Network.BITCOIN

BLOCKTRAIL_API_KEY = os.getenv('BLOCKTRAIL_API_KEY')
SPRUNED_SERVICE_URL = 'https://spruned.mempool.co/data/'
