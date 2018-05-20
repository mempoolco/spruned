from collections import OrderedDict


class MempoolRepository(OrderedDict):
    def __init__(self, mempool_min_fee=0, max_mempool_size=50000, **kw):
        super().__init__(**kw)
        self._max_mempool_size = max_mempool_size
        self._transactions_sort = list()

        self._mempool_projection = {
            "size": 0,
            "bytes": 0,
            "usage": 0,
            "maxmempool": max_mempool_size,
            "mempoolminfee": mempool_min_fee
        }

    def get_info(self):
        return ''

    def get_raw_mempool(self):
        return ''

    def _remove_transactions_for_bytes(self, size: int):
        removed = 0
        keygen = (x for x in self.keys())
        while removed < size:
            transaction = self[next(keygen)]
            removed += transaction.size()
            self.remove_transaction(transaction.hash())

    def update_mempool_projection(self, transaction, action='add'):
        if action == 'add':
            expected_size = self._mempool_projection['bytes'] + transaction.size()
            if expected_size > self._mempool_projection['maxmempool']:
                self._remove_transactions_for_bytes(transaction.size())
            self._mempool_projection['size'] += 1
            self._mempool_projection['bytes'] += transaction.size()
            self._mempool_projection['usage'] += transaction.size()  # ??
        elif action == 'remove':
            self._mempool_projection['size'] -= 1
            self._mempool_projection['bytes'] -= transaction.size()
            self._mempool_projection['usage'] -= transaction.size()  # ??
        else:
            raise ValueError()

    def add_transaction(self, transaction):
        self[transaction.hash()] = transaction
        self.update_mempool_projection(transaction, action='add')
        self._transactions_sort.append([transaction.hash(), transaction.size()])

    def remove_transaction(self, transaction):
        del self[transaction.hash()]
        self.update_mempool_projection(transaction, action='remove')
