import os
import json
import asyncio

from spruned.daemon.electrod.electrod_connection import ElectrodConnectionPool
from spruned.daemon.electrod.electrod_interface import ElectrodInterface


def build(network, loop=asyncio.get_event_loop()):  # pragma: no cover
    def load_electrum_servers(network):
        _current_path = os.path.dirname(os.path.abspath(__file__))
        with open(_current_path + '/electrum_servers.json', 'r') as f:
            servers = json.load(f)
        return servers[network]

    electrod_pool = ElectrodConnectionPool(
        connections=network["electrum_concurrency"], peers=load_electrum_servers(network["electrum_servers"])
    )
    electrod_interface = ElectrodInterface(electrod_pool, loop)
    return electrod_pool, electrod_interface

