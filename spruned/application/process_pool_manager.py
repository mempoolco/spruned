from concurrent.futures.process import ProcessPoolExecutor


class ProcessPoolManager:
    def __init__(self, parallelism=4):
        self._executor = None
        self._parallelism = parallelism

    def initialize(self):
        self._executor = ProcessPoolExecutor(max_workers=self._parallelism)

    @property
    def executor(self):
        return self._executor

    def restart(self):
        self._executor.shutdown(wait=True)
        self.initialize()
