class MempoolObserver:
    def __init__(self, mempool_storage):
        self.mempool_storage = mempool_storage

    def on_transaction(self, transaction):
        if transaction.hash not in self.mempool_storage.keys():
            self.mempool_storage.add_transaction(transaction)

    def on_block(self, block):
        raise NotImplementedError

