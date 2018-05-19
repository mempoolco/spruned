import os
import json
import asyncio


def load_electrum_servers(ctx):  # pragma: no cover
    network = ctx.get_network()
    _local, local_servers = ctx.datadir + '/electrum_servers.json', []
    _current_path = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(_local) and os.path.isfile(_local):
        with open(_local, 'r') as f:
            local_servers = json.load(f)
    with open(_current_path + '/electrum_servers.json', 'r') as f:
        hardcoded_servers = json.load(f)
        electrum_servers = hardcoded_servers[network['electrum_servers']]
        _s = [s[0] for s in electrum_servers]
    harcoded_servers_set = set(_s)
    local_servers = [local_server for local_server in local_servers if local_server[0] not in harcoded_servers_set]
    return local_servers + electrum_servers


def save_electrum_servers(peers: set):  # pragma: no cover
    from spruned.application.context import ctx
    _local = ctx.datadir + '/electrum_servers.json'
    if os.path.exists(_local) and os.path.isfile(_local):
        with open(_local, 'r') as fr:
            servers = list(set(json.load(fr)['electrum_servers']) | peers)
    else:
        servers = list(peers)
    with open(_local, 'w') as fw:
        json.dump({'electrum_servers': [[s, 's'] for s in servers]}, fw)
    return True


def build(ctx, loop=asyncio.get_event_loop()):  # pragma: no cover
    from spruned.daemon.electrod.electrod_connection import ElectrodConnectionPool
    from spruned.daemon.electrod.electrod_interface import ElectrodInterface
    network = ctx.get_network()
    electrod_pool = ElectrodConnectionPool(
        connections=network["electrum_concurrency"], peers=load_electrum_servers(ctx)
    )
    electrod_interface = ElectrodInterface(electrod_pool, loop)
    return electrod_pool, electrod_interface
