from typing import Tuple
import aiomas


class ElectrodRPCServer:
    router = aiomas.rpc.Service()

    def __init__(self, endpoint: (str, Tuple), repository):
        self.endpoint = endpoint
        self.interface = None
        self.repo = repository

    def set_interface(self, interface):
        assert not self.interface, "RPC Server already initialized"
        self.interface = interface

    async def start(self):
        return await aiomas.rpc.start_server(self.endpoint, self)

    @router.expose
    async def getrawtransaction(self, txid: str, verbose=False):
        return await self.interface.getrawtransaction(txid)

    @router.expose
    async def getblockhash(self, height: int):
        return self.repo.getblockhash(height)

    @router.expose
    async def getblockheight(self, blockhash: int):
        return self.repo.getblockheight(blockhash)
