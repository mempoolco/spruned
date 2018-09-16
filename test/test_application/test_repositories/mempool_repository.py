import asyncio

import time


class MempoolRepository:
    def __init__(self, max_size_bytes=50000):
        self._transactions = {}
        self._projection = {
            "size": 0,
            "bytes": 0,
            "maxmempool": self._max_mempool_size_bytes,
            "last_update": None
        }
        self._max_mempool_size_bytes = max_size_bytes
        self.project_lock = asyncio.Lock()
        self._outpoints = {}

    def dump(self, filepointer):
        pass

    def load(self, filepointer):
        pass

    def add_seen(self, txid, seen_by) -> bool:
        tx = self._transactions.get(txid, None)
        if not tx:
            self._transactions[txid] = {
                "txid": txid,
                "seen_by": seen_by,
                "seen_at_height": None,
                "seen_at": int(time.time()),
                "received_at": None,
                "received_at_height": None,
                "bytes": None,
                "outpoints": None,
                "size": None
            }
        return bool(not tx)

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
            pass
        return bool(not double_spend)

    def _add_outpoints(self, data):
        for outpoint in data["outpoints"]:
            if self._outpoints.get(outpoint):
                self._outpoints[outpoint].add(data["txid"])
            else:
                self._outpoints[outpoint] = {data["txid"], }

    def _delete_outpoint(self, data: dict):
        for outpoint in data["outpoints"]:
            if len(self._outpoints[outpoint]) == 1:
                del self._outpoints[outpoint]
            else:
                del self._outpoints[outpoint][data["txid"]]

    def remove_transaction(self, txid):
        data = self._transactions.pop(txid)
        self._project_transaction(data, '-')
        self._delete_outpoint(data)

    async def _project_transaction(self, data, action='add'):
        await self.project_lock.acquire()
        try:
            if action == '+':
                self._projection = {
                    "size": self._projection["size"] + data["size"],
                    "bytes": self._projection["bytes"] + data["bytes"],
                    "maxmempool": self._max_mempool_size_bytes,
                }
            elif action == '-':
                self._projection = {
                    "size": self._projection["size"] - data["size"],
                    "bytes": self._projection["bytes"] - data["bytes"],
                    "maxmempool": self._max_mempool_size_bytes,
                }
            else:
                raise ValueError
        finally:
            self.project_lock.release()

    def get_missings(self) -> set():
        items = self._transactions.items()
        return (k for k, v in items if not v)

    def get_mempool_info(self):
        return self._projection and self._projection

    def get_txids(self):
        return (x for x in self._transactions.keys())

    async def on_new_block(self, verbose_block: dict):
        block_txs = set(verbose_block['tx'])
        mempool = set(self._transactions.keys())
        in_mempool = block_txs & mempool
        txbytes = 0
        i = 0
        for txid in in_mempool:
            data = self._transactions.pop(txid)["bytes"]
            txbytes += data
            self._delete_outpoint(data)
            i += 1
        await self.project_lock.acquire()
        try:
            self._projection = {
                "size": self._projection["size"] - i,
                "bytes": self._projection["bytes"] - txbytes,
                "maxmempool": self._max_mempool_size_bytes,
            }
        finally:
            self.project_lock.release()
