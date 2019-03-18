import json
import os
import random
from json import JSONDecodeError
from spruned.application.context import Context
from spruned.daemon.bitcoin_p2p import utils


def build(ctx: Context):  # pragma: no cover
    network = ctx.get_network()
    assert isinstance(network, dict), network
    from spruned.daemon.bitcoin_p2p.p2p_connection import P2PConnectionPool
    from spruned.daemon.bitcoin_p2p.p2p_interface import P2PInterface
    peers = load_p2p_peers()
    pool = P2PConnectionPool(
        connections=8, batcher_timeout=15, network=network['pycoin'], ipv6=False, proxy=str(ctx.proxy), context=ctx
    )
    for peer in peers:
        pool.add_peer(peer)
    interface = P2PInterface(pool, network=network['pycoin'])
    if ctx.tor:
        async def _no_dns_bootstrap(*_, **__):
            return load_p2p_peers()
        interface.peers_bootstrapper = _no_dns_bootstrap
    return pool, interface


def load_p2p_peers():  # pragma: no cover
    from spruned.application.context import ctx
    _local = ctx.datadir + '/p2p_peers.json'
    local_peers = []
    if os.path.exists(_local) and os.path.isfile(_local):
        with open(_local, 'r') as fr:
            try:
                local_peers = json.load(fr)['p2p_peers']
            except JSONDecodeError:
                os.remove(_local)
    network = ctx.get_network()
    _current_path = os.path.dirname(os.path.abspath(__file__))
    with open(_current_path + '/p2p_peers.json', 'r') as f:
        hardcoded_peers = json.load(f)[network['alias']]
    local_peers = [peer for peer in local_peers if peer not in hardcoded_peers]
    peers = local_peers + hardcoded_peers
    if ctx.tor:
        return [s for s in peers if '.onion' in s[0]]
    else:
        return [s for s in peers if '.onion' not in s[0]]


def save_p2p_peers(peers, max_peers=5120, ipv6=False, shuffle=True):  # pragma: no cover
    from spruned.application.context import ctx
    from shutil import copyfile
    peers = peers[:64]  # fixme
    filename = '/p2p_peers.json'
    _local = ctx.datadir + filename
    _templocal = ctx.datadir + filename.replace('/', '/~')
    current_peers = load_p2p_peers()
    _current_ips = [x[0] for x in current_peers]
    changed = False
    for peer in peers:
        if peer[0] not in _current_ips:
            changed = True
            current_peers.append(peer)
    shuffle and random.shuffle(current_peers)
    current_peers = current_peers[:max_peers] if ipv6 else [p for p in current_peers if ':' not in p[0]][:max_peers]
    if changed:
        with open(_templocal, 'w') as fw:
            json.dump({'p2p_peers': current_peers}, fw, indent=2)
        copyfile(_templocal, _local)
        os.remove(_templocal)
    if ctx.tor:
        return [s for s in current_peers if '.onion' in s[0]]
    else:
        return [s for s in current_peers if '.onion' not in s[0]]
