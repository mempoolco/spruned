from spruned.service.storage import StorageFileInterface


class CacheFileInterface(StorageFileInterface):
    def __init__(self, directory, cache_limit=None, compress=True):
        super().__init__(directory, cache_limit=cache_limit, compress=compress)
