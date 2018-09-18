import time


class MempoolRepository:
    def __init__(self, max_size_bytes=50000):
        self._max_mempool_size_bytes = max_size_bytes
        self._transactions = dict()
        self._double_spends = dict()
        self._double_spends_by_outpoint = dict()
        self._outpoints = dict()
        self._projection = {
            "size": 0,
            "bytes": 0,
            "maxmempool": self._max_mempool_size_bytes,
            "last_update": None
        }
        self._forget_pool = {}

    @property
    def transactions(self):
        return self._transactions

    def dump(self, filepointer):
        pass

    def load(self, filepointer):
        pass

    def add_seen(self, txid, seen_by) -> bool:
        if txid in self._transactions and self._transactions[txid]['received_at'] \
                or txid in self._double_spends or txid in self._forget_pool:
            return False

        if txid not in self._transactions:
            self._transactions[txid] = {
                "txid": txid,
                "seen_by": {seen_by},
                "seen_at_height": None,
                "seen_at": int(time.time()),
                "received_at": None,
                "received_at_height": None,
                "bytes": None,
                "outpoints": None,
                "size": None
            }
        else:
            self._transactions[txid]['seen_by'].add(seen_by)
        return True

    @staticmethod
    def _is_rbf(data):
        return False  # TODO

    def add_transaction(self, txid, data) -> bool:
        double_spend = False
        for outpoint in data["outpoints"]:
            double_spend = double_spend or self._outpoints.get(outpoint)
            if double_spend:
                break
        if not double_spend:
            self._add_outpoints(data)
            self._transactions[txid].update(
                {
                    "received_at": data["timestamp"],
                    "received_at_height": None,
                    "bytes": data["bytes"],
                    "outpoints": data["outpoints"],
                    "size": data["size"]
                }
            )
            self._project_transaction(data, '+')
        elif self._is_rbf(data):
            raise NotImplementedError()
        else:
            self._add_double_spend(data)
        return bool(not double_spend)

    def _add_outpoints(self, data):
        for outpoint in data["outpoints"]:
            if self._outpoints.get(outpoint):
                self._outpoints[outpoint].add(data["txid"])
            else:
                self._outpoints[outpoint] = {data["txid"], }

    def _add_double_spend(self, data):
        self._double_spends[data["txid"]] = data
        for outpoint in data["outpoints"]:
            if self._double_spends_by_outpoint.get(outpoint):
                self._double_spends_by_outpoint[outpoint].add(data["txid"])
            else:
                self._double_spends_by_outpoint[outpoint] = {data["txid"], }
        self._transactions.pop(data["txid"])

    def _delete_outpoints(self, data: dict):
        for outpoint in data["outpoints"]:
            if len(self._outpoints[outpoint]) == 1:
                del self._outpoints[outpoint]
            else:
                del self._outpoints[outpoint][data["txid"]]

            double_spend_txids_by_outpoint = self._double_spends_by_outpoint.pop(outpoint, [])
            for txid in double_spend_txids_by_outpoint:
                """
                remove double spends related to this transaction
                """
                self._remove_double_spend(txid)

    def remove_transaction(self, txid):
        data = self._transactions.pop(txid, None)
        if data:
            self._project_transaction(data, '-')
            self._delete_outpoints(data)
        self._add_txids_to_forget_pool(txid)

    def _remove_double_spend(self, txid):
        for outpoint in self._double_spends[txid]["outpoints"]:
            if self._double_spends_by_outpoint.get(outpoint):
                if len(self._double_spends_by_outpoint[outpoint]) == 1:
                    self._double_spends_by_outpoint.pop(outpoint)
                else:
                    self._double_spends_by_outpoint[outpoint].remove(txid)
            if outpoint in self._outpoints:
                for _txid in self._outpoints[outpoint]:
                    self.remove_transaction(_txid)
        self._double_spends.pop(txid, None)
        self._add_txids_to_forget_pool(txid)

    def _add_txids_to_forget_pool(self, *txid):
        self._forget_pool.update({tx: int(time.time()) for tx in txid})

    def _project_transaction(self, data, action='add'):
        if action == '+':
            self._projection = {
                "size": self._projection["size"] + 1,
                "bytes": self._projection["bytes"] + data["size"],
                "maxmempool": self._max_mempool_size_bytes,
            }
        elif action == '-':
            self._projection = {
                "size": self._projection["size"] - 1,
                "bytes": self._projection["bytes"] - data["size"],
                "maxmempool": self._max_mempool_size_bytes,
            }
        else:
            raise ValueError

    def get_missings(self) -> set():
        items = self._transactions.items()
        return (k for k, v in items if not v)

    def get_mempool_info(self):
        return self._projection and self._projection

    def get_txids(self):
        return (x for x in self._transactions.keys())

    def on_new_block(self, verbose_block: dict):
        self._add_txids_to_forget_pool(*verbose_block["tx"])
        for txid in verbose_block["tx"]:
            if txid in self._transactions:
                self.remove_transaction(txid)
            elif txid in self._double_spends:
                self._remove_double_spend(txid)
