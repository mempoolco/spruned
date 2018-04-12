from typing import Dict

from spruned.daemon.bitcoin_p2p import utils
from spruned.daemon.bitcoin_p2p.p2p_connection import P2PConnectionPool
from spruned.daemon.bitcoin_p2p.p2p_interface import P2PInterface


def build(network: Dict):
    assert isinstance(network, dict), network
    pool = P2PConnectionPool(connections=8, batcher_timeout=30, network=network['pycoin'])
    interface = P2PInterface(pool, network=network['pycoin'])
    return pool, interface
