import time

from pycoin.block import Block

from spruned.application.logging_factory import Logger


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
        if txid in self._transactions or txid in self._double_spends or txid in self._forget_pool:
            return False
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
            tx = {
                    "received_at": data["timestamp"],
                    "received_at_height": None,
                    "outpoints": data["outpoints"],
                    "size": data["size"]
                }
            if not self._transactions.get(txid):
                self._transactions[txid] = tx
            else:
                self._transactions[txid].update(tx)
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

    def _project_transaction(self, data, action='+'):
        if action == '+':
            self._projection = {
                "size": self._projection["size"] + 1,
                "bytes": self._projection["bytes"] + data["size"],
                "maxmempool": self._max_mempool_size_bytes,
                "last_update": int(time.time())
            }
        elif action == '-':
            self._projection = {
                "size": self._projection["size"] - 1,
                "bytes": self._projection["bytes"] - data["size"],
                "maxmempool": self._max_mempool_size_bytes,
                "last_update": int(time.time())
            }
        else:
            raise ValueError

    def get_missings(self) -> set():
        items = self._transactions.items()
        return (k for k, v in items if not v)

    def get_mempool_info(self):
        return self._projection and self._projection

    def get_raw_mempool(self, verbose):
        txitems = self._transactions.items()
        if verbose:
            return {
                k: {
                    "size": v['size'],
                    "fee": 0,
                    "modifiedfee": 0,
                    "time": v['received_at'],
                    "height": v['received_at_height'] or 0,
                    "descendantcount": 0,
                    "descendantsize": 0,
                    "descendantfees": 0,
                    "ancestorcount": 0,
                    "ancestorsize": 0,
                    "ancestorfees": 0,
                    "depends": [
                    ]
                } for k, v in txitems
            }
        else:
            return [k for k, v in txitems]

    def get_txids(self):
        return (x for x in self._transactions.keys())

    def on_new_block(self, block_object: Block):
        txs = [str(x.w_hash()) for x in block_object.txs]
        txs.extend([str(x.hash()) for x in block_object.txs])
        removed = []
        self._add_txids_to_forget_pool(*txs)
        for txid in txs:
            if txid in self._transactions:
                self.remove_transaction(txid)
                removed.append(txid)
            elif txid in self._double_spends:
                self._remove_double_spend(txid)
                removed.append(txid)
        return txs, removed
