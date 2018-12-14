class AsyncEventsCollector:
    def __init__(self):
        self._block_observers = []
        self._transaction_observers = []
        self._blockheader_observers = []
        self._address_observer = []

    def add_on_new_address(self, observer):
        self._address_observer.append(observer)

    def add_on_new_block_observer(self, observer):
        self._block_observers.append(observer)

    def add_on_new_transaction_observer(self, observer):
        self._transaction_observers.append(observer)

    def add_on_new_blockheader_observer(self, observer):
        self._blockheader_observers.append(observer)

    async def on_new_block(self):
        pass

    async def on_new_transaction(self, *a, **kw):
        pass

    async def on_new_blockheader(self, *a, **kw):
        pass

    async def on_new_address(self, *a, **kw):
        pass
