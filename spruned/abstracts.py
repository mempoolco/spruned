import abc


class RPCAPIService(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def getblock(self, blockhash):
        pass  # pragma: no cover

    @abc.abstractmethod
    def getrawtransaction(self, txid, **kwargs):
        pass  # pragma: no cover

    @property
    @abc.abstractmethod
    def available(self) -> bool:
        pass  # pragma: no cover


class StorageInterface(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def set(self, *a, ttl: int=0):
        pass  # pragma: no cover

    @abc.abstractmethod
    def get(self, *a):
        pass  # pragma: no cover

    @abc.abstractmethod
    def remove(self, *a):
        pass  # pragma: no cover


class HeadersRepository(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def get_best_header(self):
        pass  # pragma: no cover

    @abc.abstractmethod
    def get_header_for_hash(self, blockhash: str):
        pass  # pragma: no cover

    @abc.abstractmethod
    def get_header_at_height(self, blockheight: int):
        pass  # pragma: no cover

    @abc.abstractmethod
    def save_header(self, blockhash: str, blockheight: int, headerbytes: bytes, prev_block_hash: str):
        pass  # pragma: no cover
