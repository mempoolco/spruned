import asyncio
import time
from statistics import median

from spruned.daemon.electrod.electrod_connection import ElectrodConnection


class NotEnoughDataException(Exception):
    pass

class NoPeersException(Exception):
    pass


class EstimateFeeConsensusProjector:
    def __init__(self, d=0.1, max_age=900, time_window=120):
        self._max_age = max_age
        self._time_window = time_window
        self._d = d

    def _produce_projection(self, data, p, agreement):
        response = {
            "agreement": 0,
            "points": [entry["value"] for entry in data],
            "median": 0,
            "average": 0,
            "timestamp": median([entry["timestamp"] for entry in data]),
            "disagree": [],
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
        return response

    def project(self, data, participants, agreement=80):
        evaluate = []
        now = int(time.time())
        for d in data:
            if d["value"] and now - self._time_window > d["timestamp"]:
                evaluate.append(d)
        if len(evaluate) >= participants:
            return self._produce_projection(data, participants, agreement)
        raise NotEnoughDataException


class EstimateFeeConsensusCollector:
    def __init__(self, connectionclass=ElectrodConnection):
        self._rates = set()
        self._data = dict()
        self._max_age = 120
        self._permanent_connections_pool = None
        self._connectionclass = connectionclass
        self._peers = set()

    def add_peer(self, peer):
        self._peers.add(peer)

    def add_permanent_connections_pool(self, connectionpool):
        self._permanent_connections_pool = connectionpool

    def set_max_age(self, value):
        self._max_age = value

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
            if self._data.get(peer):
                pass
            self._data[peer] = {
                "rates": {r: None for r in self._rates},
                'peer': peer,
                "score": 0
            }

    def add_rate(self, *rate: list):
        diff = set(rate) - self._rates
        if diff:
            self._rates = self._rates & diff
        for newrate in diff:
            for peer in self._data:
                self._data[peer]["rates"][newrate] = None

    def _add_collected_rate_to_data(self, peer, rate, value, timestamp=None):
        self._data[peer]["rates"][rate] = [value, timestamp or int(time.time())]

    async def collect(self, members=8):
        if not self.is_consensus_pool_established(members):
            self._establish_consensus_pool(members)

        expired_peers = self.get_expired_consensus_members()
        if expired_peers:
            futures = []
            for peer in expired_peers:
                if self._is_active(peer) and not self._is_updated(peer):
                    futures.append(self._update(peer))
            await asyncio.gather(*futures, return_exceptions=True)
        await asyncio.sleep(5)

    def _establish_consensus_pool(self, members):
        while not self.is_consensus_pool_established(members):
            if not self._peers:
                raise NoPeersException
            self.add_peer_to_consensus(self._peers.pop())

    def is_consensus_pool_established(self, members):
        if len(self._data) < members:
            return False
        active = []
        for peer, value in self._data.items():
            if self._is_active(value):
                active.append(peer)
        return len(active) >= members

    def get_expired_consensus_members(self):
        expired = []
        for peer, value in self._data.items():
            if not self._is_updated(value):
                expired.append(peer)
        return expired

    @staticmethod
    def _is_active(peer):
        return peer['score'] >= -1

    def _is_rate_expired(self, rate):
        now = int(time.time())
        if not rate or (now > rate["timestamp"] + self._max_age):
            return True

    def _is_updated(self, peer):
        for rate, value in peer["rates"].items():
            if self._is_rate_expired(value):
                return False
        return True

    async def _update(self, peer):
        futures = []

        async def estimatefee(peer, conn, target):
            res = await conn.rpc_call('blockchain.estimatefee', target)
            return {
                'target': target,
                'peer': peer,
                'value': int(float(res) * 1000)
            }

        connection = None
        for rate, value in peer["rates"].items():
            if self._is_rate_expired(value):
                hostname, protocol = peer["peer"].split('/')
                connection = connection or self._connectionclass(hostname, protocol, keepalive=False)
                futures.append(estimatefee(peer, connection, rate))

        if connection:
            try:
                await connection.connect()
                results = await asyncio.gather(*futures, return_exceptions=True)
                for result in results:
                    if not isinstance(result, Exception):
                        self._data[result["peer"]][result["target"]] = result["value"]
                    else:
                        self._data[peer["peer"]]["score"] -= 1

                await connection.disconnect()
                del connection
            except Exception as e:
                self._data[peer["peer"]]["score"] -= 1
