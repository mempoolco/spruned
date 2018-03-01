from typing import Tuple, Dict
import aiomas


class ElectrodRPCServer:
    router = aiomas.rpc.Service()

    def __init__(self, endpoint: (str, Tuple), repository):
        self.endpoint = endpoint
        self.interface = None
        self.repo = repository

    def _serialize_header(self, header: Dict) -> Dict:
        return header

    def set_interface(self, interface):
        assert not self.interface, "RPC Server already initialized"
        self.interface = interface

    def enable_blocks_api(self):
        pass

    def disable_blocks_api(self):
        pass

    async def start(self):
        return await aiomas.rpc.start_server(self.endpoint, self)

    @router.expose
    async def getrawtransaction(self, txid: str, verbose=False):
        return await self.interface.getrawtransaction(txid)

    @router.expose
    async def getblockhash(self, height: int):
        return self.repo.get_block_hash(height)

    @router.expose
    async def getblockheight(self, blockhash: str):
        return self.repo.get_block_height(blockhash)

    @router.expose
    async def getblockheader(self, blockhash: str):
        header = await self.repo.get_block_header(blockhash)
        return self._serialize_header(header)

    @router.expose
    async def sendrawtransaction(self, rawtransaction: str):
        return await self.interface.sendrawtransaction(rawtransaction)

    @router.expose
    async def estimatefee(self, blocks: int):
        return await self.interface.estimatefee(blocks)

    @router.expose
    async def getmempoolinfo(self):
        return await self.interface.getmempoolinfo()
