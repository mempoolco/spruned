import time
from statistics import median


class NotEnoughDataException(Exception):
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
            "value": 0,
            "timestamp": median([entry["timestamp"] for entry in data]),
            "disagree": [],
        }
        med = response["value"] = median(response["points"])

        def evaluate_value(_v):
            return bool(med - med*self._d < _v < med + med*self._d)

        perc = int(100 / p)
        for entry in data:
            if evaluate_value(entry["value"]):
                response["agreement"] += perc
            else:
                response["disagree"].append(entry["peer"])
        response["agree"] = (response["agreement"] >= agreement)
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
