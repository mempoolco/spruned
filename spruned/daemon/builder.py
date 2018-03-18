import asyncio
import json
from typing import Tuple

import os

from spruned.daemon.daemon_service import DaemonService
from spruned.daemon.electrod.electrod_connection import ElectrodConnectionPool
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon.headers_reactor import HeadersReactor


def build_reactor_and_daemon(headers_repository, interface, loop=asyncio.get_event_loop()) \
        -> Tuple[HeadersReactor, DaemonService]:  # pragma: no cover

    headers_reactor = HeadersReactor(headers_repository, interface, loop=loop)
    daemon_service = DaemonService(interface)
    return headers_reactor, daemon_service


def build_electrod_interface(connections=3, loop=asyncio.get_event_loop()):  # pragma: no cover
    def load_electrum_servers(network):
        _current_path = os.path.dirname(os.path.abspath(__file__))
        with open(_current_path + '/electrod/electrum_servers.json', 'r') as f:
            servers = json.load(f)
        return servers[network]

    electrod_pool = ElectrodConnectionPool(
        connections=connections, peers=load_electrum_servers("bc_mainnet")
    )
    electrod_interface = ElectrodInterface(electrod_pool, loop)
    return electrod_interface
