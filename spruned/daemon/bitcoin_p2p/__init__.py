import json
import os
from json import JSONDecodeError
from typing import Dict, Tuple
from spruned.daemon.bitcoin_p2p import utils


def build(network: Dict):
    assert isinstance(network, dict), network
    from spruned.daemon.bitcoin_p2p.p2p_connection import P2PConnectionPool
    from spruned.daemon.bitcoin_p2p.p2p_interface import P2PInterface
    pool = P2PConnectionPool(connections=8, batcher_timeout=15, network=network['pycoin'], ipv6=False)
    interface = P2PInterface(pool, network=network['pycoin'])
    return pool, interface


def load_p2p_peers():
    from spruned.application.context import ctx
    _local = ctx.datadir + '/p2p_peers.json'
    if os.path.exists(_local) and os.path.isfile(_local):
        with open(_local, 'r') as fr:
            try:
                return json.load(fr)['p2p_peers']
            except JSONDecodeError:
                os.remove(_local)
    return []


def save_p2p_peers(peers):  # pragma: no cover
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
    if changed:
        with open(_templocal, 'w') as fw:
            json.dump({'p2p_peers': current_peers}, fw, indent=2)
        copyfile(_templocal, _local)
        os.remove(_templocal)
    return current_peers
