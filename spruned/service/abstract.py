import abc


class RPCAPIService(metaclass=abc.ABCMeta):
    @abc.abstractmethod
    def getblock(self, blockhash):
        pass  # pragma: no cover

    @abc.abstractmethod
    def getrawtransaction(self, txid, **kwargs):
        pass  # pragma: no cover

    @abc.abstractmethod
    def getblockheader(self, blockhash):
        pass  # pragma: no cover
