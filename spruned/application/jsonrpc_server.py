import binascii
from aiohttp import web
from jsonrpcserver.aio import methods
from jsonrpcserver import config

config.schema_validation = False


class JSONRPCServer:
    def __init__(self, host, port, username, password):
        self.username = username
        self.password = password
        self.host = host
        self.port = port
        self.vo_service = None

    def set_vo_service(self, vo_service):
        self.vo_service = vo_service

    async def _handle(self, request):
        request = await request.text()
        response = await methods.dispatch(request)
        if "error" in response["result"]:
            return web.json_response(response["result"], status=400)
        return web.json_response(response, status=response.http_status)

    async def start(self):
        app = web.Application()
        app.router.add_post('/', self._handle)
        runner = web.AppRunner(app)
        await runner.setup()
        methods.add(self.getblockchaininfo)
        methods.add(self.getblockhash)
        methods.add(self.getblockheight)
        methods.add(self.getblock)
        methods.add(self.getrawtransaction)
        methods.add(self.getbestblockhash)
        return await web.TCPSite(runner, host=self.host, port=self.port).start()

    async def getblock(self, blockhash: str):
        try:
            binascii.unhexlify(blockhash)
        except binascii.Error:
            return {"error": {"code": -5, "message": "Block not found"}}
        response = await self.vo_service.getblock(blockhash)
        if not response:
            return {"error": {"code": -5, "message": "Block not found"}}
        return response

    async def getrawtransaction(self, txid: str, verbose=False):
        raise NotImplementedError

    async def getblockchaininfo(self):
        raise NotImplementedError

    async def getblockhash(self, blockheight: int):
        raise NotImplementedError

    async def getblockheight(self, blockhash: str):
        raise NotImplementedError

    async def getbestblockhash(self):
        raise NotImplementedError
