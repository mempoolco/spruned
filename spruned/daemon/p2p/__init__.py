from spruned.daemon.p2p import utils
from spruned.daemon.p2p.p2p_connection import P2PConnectionPool
from spruned.daemon.p2p.p2p_interface import P2PInterface


def build(network):
    assert network
    pool = P2PConnectionPool(connections=3)
    interface = P2PInterface(pool)
    return pool, interface
