import abc


class CacheInterface(metaclass=abc.ABCMeta):
    def set(self, *a, ttl: int=0):
        pass  # pragma: no cover

    def get(self, *a):
        pass  # pragma: no cover

    def remove(self, *a):
        pass  # pragma: no cover
