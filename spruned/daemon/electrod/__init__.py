import os
import json
import asyncio

from spruned.daemon.electrod.electrod_connection import ElectrodConnectionPool
from spruned.daemon.electrod.electrod_interface import ElectrodInterface


def build(network, connections=5, loop=asyncio.get_event_loop()):  # pragma: no cover
    assert network

    def load_electrum_servers(network):
        _current_path = os.path.dirname(os.path.abspath(__file__))
        with open(_current_path + '/electrum_servers.json', 'r') as f:
            servers = json.load(f)
        return servers[network]

    electrod_pool = ElectrodConnectionPool(
        connections=connections, peers=load_electrum_servers("bc_mainnet")
    )
    electrod_interface = ElectrodInterface(electrod_pool, loop)
    return electrod_pool, electrod_interface

