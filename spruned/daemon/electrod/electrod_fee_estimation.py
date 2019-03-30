import asyncio
import json
import time
from statistics import median

import random

from spruned.application.context import ctx
from spruned.application.logging_factory import Logger
from spruned.daemon.electrod.electrod_connection import ElectrodConnection


class NotEnoughDataException(Exception):
    pass


class NoPeersException(Exception):
    pass


class EstimateFeeConsensusProjector:
    def __init__(self, distance=0.1, time_window=900, max_age=120):
        self._max_age = max_age
        self._time_window = time_window
        self._d = distance

    def _produce_projection(self, data, p, agreement):
        response = {
            "agreement": 0,
            "points": [entry["value"] for entry in data],
            "median": 0,
            "average": 0,
            "timestamp": median([entry["timestamp"] for entry in data]),
            "disagree": []
        }
        med = response["median"] = median(response["points"])

        def evaluate_value(_v):
            return bool(med - med*self._d < _v < med + med*self._d)

        perc = int(100 / p)
        agreed = []
        for entry in data:
            if evaluate_value(entry["value"]):
                response["agreement"] += perc
                agreed.append(entry["value"])
            else:
                response["disagree"].append(entry["peer"])
        response["agree"] = (response["agreement"] >= agreement)
        response["average"] = int(sum(agreed) / len(agreed))
        response["average_satoshi_per_kb"] = round((response["average"]*1000)/10**8, 8)
        return response

    def project(self, data, members, agreement=80):
        evaluate = []
        now = int(time.time())
        for d in data:
            if self._max_age + d["timestamp"] > now:
                evaluate.append(d)
        if len(evaluate) >= members:
            return self._produce_projection(data, members, agreement)
        raise NotEnoughDataException


class EstimateFeeConsensusCollector:
    def __init__(self, connectionclass=ElectrodConnection, proxy=None, time_window=120, max_age=900):
        self._rates = set()
        self._data = dict()
        self._time_window = time_window
        self._permanent_connections_pool = None
        self._connectionclass = connectionclass
        self._peers = list()
        self._max_age = max_age
        self._collector_lock = asyncio.Lock()
        self._proxy = proxy

    @property
    def proxy(self):
        return self._proxy

    def add_peer(self, peer):
        if peer not in self._peers:
            self._peers.append(peer)

    def add_permanent_connections_pool(self, connectionpool):
        self._permanent_connections_pool = connectionpool

    def to_json(self):
        return {
            "data": self._data,
            "max_age": self._max_age
        }

    @classmethod
    def from_json(cls, data) -> 'EstimateFeeConsensusCollector':
        i = cls()
        i._data = data["data"]
        i._max_age = data["max_age"]
        return i

    def add_peer_to_consensus(self, *peers):
        for peer in peers:
            permanent = False
            if 'permanent|' in peer:
                peer = peer.replace('permanent|', '')
                permanent = True
            if self._data.get(peer):
                pass
            self._data[peer] = {
                "rates": {r: None for r in self._rates},
                "peer": peer,
                "score": 5,
                "permanent": permanent
            }

    def add_rate(self, *rate):
        diff = set(rate) - self._rates
        if diff:
            self._rates = self._rates | diff
        for newrate in diff:
            for peer in self._data:
                self._data[peer]["rates"][newrate] = None

    def _add_collected_rate_to_data(self, peer, rate, value, timestamp=None):
        self._data[peer]["rates"][rate] = [value, timestamp or int(time.time())]

    def reset_data(self):
        self._data = {}

    async def collect(self, rates=None, members=ctx.max_electrum_connections):
        _ = rates and [self.add_rate(rate) for rate in rates if rate not in self._rates]
        if not self.is_consensus_pool_established(members):
            self._establish_consensus_pool(members)
        expired_peers = self.get_expired_consensus_members()
        if expired_peers:
            futures = []
            connections = []
            permanents = []
            for peer in expired_peers:
                hostname, protocol = peer.split('/')
                established = self._permanent_connections_pool and \
                              self._permanent_connections_pool.established_connections or []
                permanent = hostname in [peer.hostname for peer in established]
                if permanent:
                    permanents.append(hostname)
                    connection = self._permanent_connections_pool.get_peer_for_hostname(hostname)
                else:
                    connection = self._connectionclass(
                        hostname, protocol, keepalive=False, timeout=self.proxy and 10 or 5, proxy=self.proxy
                    )
                if self._is_active(self._data[peer]) and not self._is_updated(self._data[peer], rates):
                    futures.append(self._update(peer, connection, rates))
                    if futures:
                        try:
                            await connection.connect(
                                ignore_version=True, disable_callbacks=True, short_term=True
                            )
                            connections.append(connection)
                        except:
                            self.penalize_peer(peer)
                            Logger.electrum.debug('Fee estimation, penalizing peer: %s', peer)
            await asyncio.gather(*futures, return_exceptions=True)
            for connection in connections:
                if connection.hostname in permanents:
                    continue
                try:
                    await connection.disconnect()
                except:
                    pass

    def _establish_consensus_pool(self, members: int):
        while not self.is_consensus_pool_established(members):
            if self._permanent_connections_pool:
                permanents = [
                    '%s/%s' % (x.hostname, x.protocol) for x in self._permanent_connections_pool.established_connections
                ]
                for peer in permanents:
                    if not self._data.get(peer, None):
                        self.add_peer_to_consensus('permanent|{}'.format(peer))

            if not self._peers:
                raise NoPeersException
            peer = random.choice(self._peers)
            self.add_peer_to_consensus(peer)

    def is_consensus_pool_established(self, members: int):
        if self._permanent_connections_pool:
            established = [
                '%s/%s' % (x.hostname, x.protocol) for x in self._permanent_connections_pool.established_connections
            ]
            for address, peer in self._data.items():
                if peer.get('permanent') and address not in established:
                    self._data.pop(address)
        if len(self._data) < members:
            return False
        active = []
        to_remove = []
        for peer, value in self._data.items():
            if self._is_active(value):
                active.append(peer)
            else:
                to_remove.append(peer)
        for peer in to_remove:
            self._data.pop(peer)
        return len(active) >= members

    def get_expired_consensus_members(self, rates=None):
        expired = []
        for peer, value in self._data.items():
            if not self._is_updated(value, rates) and self._is_active(value):
                expired.append(peer)
        return expired

    def _is_active(self, peer):
        return peer['score'] >= 0

    def _is_rate_expired(self, rate):
        now = int(time.time())
        if rate is None or (now > rate["timestamp"] + self._max_age):
            return True

    def _is_updated(self, peer, rates):
        if rates is not None:
            container = {k: v for k, v in peer["rates"].items() if k in rates}.items()
        else:
            container = peer["rates"].items()
        for rate, value in container:
            if self._is_rate_expired(value):
                return False
        return True

    def penalize_peer(self, peer):
        self._data[peer]["score"] -= 1

    def reward_peer(self, peer):
        self._data[peer]["score"] += 1

    async def _update(self, peer, connection, rates=None):
        futures = []

        async def estimatefee(peer, conn, target):
            res = await conn.client.RPC("blockchain.estimatefee", target)
            if not res:
                return
            return {
                "target": target,
                "peer": peer,
                "value": int((float(res) * 10**8)/1000)
            }
        if rates is not None:
            container = {k: v for k, v in self._data[peer]["rates"].items() if k in rates}.items()
        else:
            container = self._data[peer]["rates"].items()
        for rate, value in container:
            if self._is_rate_expired(value):
                futures.append(estimatefee(peer, connection, rate))

        if connection:
            results = await asyncio.gather(*futures, return_exceptions=True)
            for result in results:
                if result and not isinstance(result, Exception):
                    self._data[result["peer"]]["rates"][result["target"]] = {
                        "value": result["value"],
                        "timestamp": int(time.time()),
                        "peer": result["peer"],
                        "target": result["target"]
                    }
                    self.reward_peer(peer)
                else:
                    self.penalize_peer(peer)

    def rates_available(self, consensus):
        data = []
        for peer, peerdata in self._data.items():
            data.append(peerdata and self._is_updated(peerdata, self._rates))
        if len([x for x in data if x]) >= consensus:
            return True

    def get_data(self, rates=None):
        return [data for _, data in self._data.items() if self._is_updated(data, rates) and self._is_active(data)]

    def get_jsondata(self, rates=None):
        return json.dumps(self.get_data(rates), indent=2)

    def get_rates(self, *value):
        data = []
        for v in value:
            assert v in self._rates
            data.extend([x["rates"][v] for x in self.get_data([v])])
        return data
