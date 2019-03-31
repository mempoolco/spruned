import time
from statistics import median
from spruned.daemon import exceptions


class NotEnoughDataException(Exception):
    pass


class NoPeersException(Exception):
    pass


class EstimateFeeConsensusProjector:
    def __init__(self, distance=0.1):
        self._d = distance

    def _produce_projection(self, data, agreement):
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

        perc = 100 / len(data)
        agreed = []
        for entry in data:
            if evaluate_value(entry["value"]):
                response["agreement"] += perc
                agreed.append(entry["value"])
            else:
                response["disagree"].append(entry["hostname"])
        response["agree"] = (response["agreement"] >= agreement)
        response["average"] = int(sum(agreed) / len(agreed))
        response["average_satoshi_per_kb"] = round((response["average"]*1000)/10**8, 8)
        response["agreement"] = int(response["agreement"])
        return response

    def project(self, data, agreement=60):
        return self._produce_projection(data, agreement)


class EstimateFeeConsensusCollector:
    def __init__(self, max_age=300, consensus=3):
        self._rates = set()
        self._data = dict()
        self._permanent_connections_pool = None
        self._max_age = max_age
        self._consensus = consensus
        self._locks = {}

    def add_permanent_connections_pool(self, connectionpool):
        self._permanent_connections_pool = connectionpool

    def add_rate(self, rate: int):
        self._rates.add(rate)

    async def collect(self, rate: int):
        if self._consensus > len(self._permanent_connections_pool.established_connections):
            raise exceptions.NoPeersException
        for connection in self._permanent_connections_pool.established_connections:
            valid = self.get_valid_consensus_members_for_rate(rate)
            if len(valid) >= self._consensus:
                return True

            if connection.hostname not in valid:
                await self._update(connection, rate)
                continue
        valid = self.get_valid_consensus_members_for_rate(rate)
        if len(valid) >= self._consensus:
            return True
        raise exceptions.NoPeersException

    def get_valid_consensus_members_for_rate(self, rate):
        valid = []
        now = int(time.time())
        for hostname, measurement in self._data.get(rate, {}).items():
            if now - measurement['timestamp'] < self._max_age:
                valid.append(hostname)
        return valid

    async def _update(self, connection, rate):
        async def estimatefee(conn, target):
            res = await conn.client.RPC("blockchain.estimatefee", target)
            if not res:
                return
            return {
                "target": target,
                "hostname": conn.hostname,
                "timestamp": int(time.time()),
                "value": int((float(res) * 10**8)/1000)
            }
        try:
            response = await estimatefee(connection, rate)
            if not self._data.get(rate):
                self._data[rate] = {}
            self._data[rate][connection.hostname] = response
        except:
            pass

    def get_rates(self, target: int):
        res = []
        now = int(time.time())
        for hostname, measurement in self._data.get(target, {}).items():
            if now - measurement['timestamp'] > self._max_age:
                continue
            res.append(measurement)
        if len(res) >= self._consensus:
            return res
