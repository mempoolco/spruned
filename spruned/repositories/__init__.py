@property
def manager(self):
    if not self._manager:
        self._manager = multiprocessing.Manager()
        self._manager.start()
    return self._manager