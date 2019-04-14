import asyncio
import time
from typing import Dict

from pycoin.block import Block


class MempoolRepository:
    def __init__(self, max_size_bytes: int=50000, loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()):
        self._max_mempool_size_bytes = max_size_bytes
        self._transactions = dict()
        self._transactions_by_time = dict()
        self._double_spends = dict()
        self._double_spends_by_outpoint = dict()
        self._outpoints = dict()
        self._projection = {
            "size": 0,
            "usage": 0,
            "bytes": 0,
            "maxmempool": self._max_mempool_size_bytes,
            "last_update": int(time.time()),
            "mempoolminfee": 0,
            "minrelaytxfee": 0
        }
        self._forget_pool = set()
        self._forget_pool_by_time = dict()
        self._last_forget_pool_clean = int(time.time())
        self._clean_lock = asyncio.Lock()
        self._forget_pool_clean_lock = asyncio.Lock()
        self.loop = loop

    @property
    def transactions(self):
        return self._transactions

    def add_seen(self, txid: str, seen_by: str) -> bool:
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

    def add_transaction(self, txid: str, data: Dict) -> bool:
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
            self._transactions_by_time[data['timestamp']] = \
                self._transactions_by_time.get(data['timestamp'], set()) | {txid}
            self._project_transaction(data, '+')
        elif self._is_rbf(data):
            raise NotImplementedError()
        else:
            self._add_double_spend(data)
        return bool(not double_spend)

    def _add_outpoints(self, data: Dict):
        for outpoint in data["outpoints"]:
            if self._outpoints.get(outpoint):
                self._outpoints[outpoint].add(data["txid"])
            else:
                self._outpoints[outpoint] = {data["txid"], }

    def _add_double_spend(self, data: Dict):
        self._double_spends[data["txid"]] = data
        for outpoint in data["outpoints"]:
            if self._double_spends_by_outpoint.get(outpoint):
                self._double_spends_by_outpoint[outpoint].add(data["txid"])
            else:
                self._double_spends_by_outpoint[outpoint] = {data["txid"], }
        self._transactions.pop(data["txid"])

    def _delete_outpoints(self, data: Dict):
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

    def remove_transaction(self, txid: str):
        data = self._transactions.pop(txid, None)
        if data:
            self._project_transaction(data, '-')
            self._delete_outpoints(data)
        self._add_txids_to_forget_pool(txid)

    def _remove_double_spend(self, txid: str):
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

    def _add_txids_to_forget_pool(self, *txid: str):
        self._forget_pool_by_time[int(time.time())] = \
            self._forget_pool_by_time.get(int(time.time()), set()) | {*txid}
        for _txid in txid:
            self._forget_pool.add(_txid)

    def _project_transaction(self, data: Dict, action: str='+'):
        now = int(time.time())
        if action == '+':
            self._projection = {
                "usage": self._projection["bytes"] + data["size"] + (32*4*self._projection['size']),
                "size": self._projection["size"] + 1,
                "bytes": self._projection["bytes"] + data["size"],
                "maxmempool": self._max_mempool_size_bytes,
                "last_update": now,
                "mempoolminfee": 0,
                "minrelaytxfee": 0

            }
            if self._projection["bytes"] > self._max_mempool_size_bytes:
                if not self._clean_lock.locked():
                    asyncio.wait_for(self._clean_lock.acquire(), timeout=None)
                    self.loop.create_task(self._clean_mempool())

        elif action == '-':
            usage = self._projection["bytes"] - data["size"] - (32*4*self._projection['size'])
            self._projection = {
                "usage": usage if usage > 0 else 0,
                "size": self._projection["size"] - 1,
                "bytes": self._projection["bytes"] - data["size"],
                "maxmempool": self._max_mempool_size_bytes,
                "last_update": now,
                "mempoolminfee": 0,
                "minrelaytxfee": 0
            }
        else:
            raise ValueError
        if now - self._last_forget_pool_clean > 60:
            if not self._forget_pool_clean_lock.locked():
                asyncio.wait_for(self._forget_pool_clean_lock.acquire(), timeout=None)
                self._forget_pool_by_time and self.loop.create_task(self._clean_forget_pool())

    async def _clean_mempool(self):
        try:
            while self._projection["bytes"] > self._max_mempool_size_bytes * 0.95:
                if not self._transactions_by_time:
                    break
                firsts = min(self._transactions_by_time, key=self._transactions_by_time.get)
                while self._transactions_by_time[firsts]:
                    self.remove_transaction(self._transactions_by_time[firsts].pop())
                del self._transactions_by_time[firsts]
        finally:
            self._clean_lock.locked() and self._clean_lock.release()

    async def _clean_forget_pool(self):
        try:
            now = int(time.time())
            min_value = self._forget_pool_by_time and min(self._forget_pool_by_time, key=self._forget_pool_by_time.get)
            while min_value + 600 < now:
                for txid in self._forget_pool_by_time[min_value]:
                    try:
                        self._forget_pool.remove(txid)
                    except KeyError:
                        pass
                del self._forget_pool_by_time[min_value]
                if not self._forget_pool_by_time:
                    break
            self._last_forget_pool_clean = now
        finally:
            self._forget_pool_clean_lock.locked() and self._forget_pool_clean_lock.release()

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
