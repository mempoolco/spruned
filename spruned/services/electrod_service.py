from spruned.application.abstracts import RPCAPIService


class ElectrodService(RPCAPIService):
    def __init__(self, coin):
        assert coin.value == 1
        self.coin = coin

    def getblock(self, blockhash):
        pass

    def getrawtransaction(self, txid, **kwargs):
        pass

    @property
    def available(self) -> bool:
        return False
