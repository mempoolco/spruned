from spruned.application.abstracts import RPCAPIService
from spruned.daemon.electrod.electrod_interface import ElectrodInterface


class ElectrodService(RPCAPIService):
    def __init__(self, interface: ElectrodInterface):
        self.interface = interface

    async def getrawtransaction(self, txid, verbose=False):
        return await self.interface.getrawtransaction(txid)

    async def getblock(self, txid, verbose=False):
        return None

    async def estimatefee(self, blocks: int):
        return await self.interface.estimatefee(blocks)

    async def sendrawtransaction(self, rawtransaction: str):
        return await self.interface.sendrawtransaction(rawtransaction)

    async def listunspents(self, address: str):
        return await self.interface.listunspents(address)

    @property
    def available(self) -> bool:
        return True
