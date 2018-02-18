import abc


class RPCAPIService(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def getblock(self, blockhash):
        pass  # pragma: no cover

    @abc.abstractmethod
    def getrawtransaction(self, txid, **kwargs):
        pass  # pragma: no cover


class CacheInterface(metaclass=abc.ABCMeta):
    def set(self, *a, ttl: int=0):
        pass  # pragma: no cover

    def get(self, *a):
        pass  # pragma: no cover

    def remove(self, *a):
        pass  # pragma: no cover