import os
import json
import asyncio


def load_electrum_servers(ctx):  # pragma: no cover
    network = ctx.get_network()
    _local, local_servers = ctx.datadir + '/electrum_servers.json', []
    _current_path = os.path.dirname(os.path.abspath(__file__))
    if os.path.exists(_local) and os.path.isfile(_local):
        with open(_local, 'r') as f:
            local_servers = json.load(f)['electrum_servers']
    with open(_current_path + '/electrum_servers.json', 'r') as f:
        hardcoded_servers = json.load(f)
        electrum_servers = hardcoded_servers[network['alias']]
        _s = [s[0] for s in electrum_servers]
    harcoded_servers_set = set(_s)
    local_servers = [local_server for local_server in local_servers if local_server[0] not in harcoded_servers_set]
    servers = local_servers + electrum_servers
    if ctx.tor:
        return [s for s in servers if '.onion' in s[0]]
    else:
        return [s for s in servers if '.onion' not in s[0]]


def save_electrum_servers(peers: set):  # pragma: no cover
    from spruned.application.context import ctx
    _local = ctx.datadir + '/electrum_servers.json'
    if os.path.exists(_local) and os.path.isfile(_local):
        with open(_local, 'r') as fr:
            servers = list(set([x[0] for x in json.load(fr)['electrum_servers']]) | peers)
    else:
        servers = list(peers)
    with open(_local, 'w') as fw:
        json.dump({'electrum_servers': [[s, 's'] for s in servers]}, fw)
    return True


def build(ctx, loop=asyncio.get_event_loop()):  # pragma: no cover
    from spruned.daemon.electrod.electrod_connection import ElectrodConnectionPool
    from spruned.daemon.electrod.electrod_interface import ElectrodInterface
    from spruned.daemon.electrod.electrod_fee_estimation import EstimateFeeConsensusProjector, \
        EstimateFeeConsensusCollector
    network = ctx.get_network()
    peers = load_electrum_servers(ctx)
    fees_collector = EstimateFeeConsensusCollector(proxy=ctx.proxy)
    _ = [fees_collector.add_peer(peer) for peer in [x[0] + '/' + x[1] for x in peers]]
    electrod_pool = ElectrodConnectionPool(
        connections=network['electrum_concurrency'],
        peers=peers,
        ipv6=False,
        proxy=ctx.proxy,
        tor=ctx.tor
    )
    electrod_interface = ElectrodInterface(
        electrod_pool,
        loop,
        fees_projector=EstimateFeeConsensusProjector(),
        fees_collector=fees_collector
    )
    electrod_interface.add_on_connected_callback(electrod_interface.bootstrap_collector)
    return electrod_pool, electrod_interface
