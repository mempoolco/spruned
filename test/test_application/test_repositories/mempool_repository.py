import asyncio


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

    def dump(self, filepointer):
        pass

    def load(self, filepointer):
        pass

    def add_seen(self, txid) -> bool:
        tx = self._transactions.get(txid, None)
        self._transactions[txid] = tx
        return bool(not tx)

    def add_transaction(self, txid, data) -> bool:
        prev = self._transactions.get(txid, None)
        self._transactions[txid] = data
        if not prev:
            self._project_transaction(data, '+')
        return bool(not prev)

    def remove_transaction(self, txid):
        data = self._transactions.pop(txid)
        self._project_transaction(data, '-')

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
            txbytes += self._transactions.pop(txid)["bytes"]
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
