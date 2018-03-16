import binascii
from aiohttp import web
from jsonrpcserver.aio import methods
from jsonrpcserver import config
from jsonrpcserver.response import ExceptionResponse

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
        if isinstance(response, ExceptionResponse):
            return web.json_response(response, status=response.http_status)
        if response and "error" in response.get("result"):
            return web.json_response(response["result"], status=400)
        return web.json_response(response, status=response.http_status)

    async def start(self):
        app = web.Application()
        app.router.add_post('/', self._handle)
        runner = web.AppRunner(app)
        await runner.setup()
        methods.add(self.estimatefee)
        methods.add(self.estimatesmartfee)
        methods.add(self.getbestblockhash)
        methods.add(self.getblockchaininfo)
        methods.add(self.getblockheader)
        methods.add(self.getblockhash)
        methods.add(self.getblock)
        methods.add(self.getblockcount)
        methods.add(self.getrawtransaction)
        methods.add(self.gettxout)

        return await web.TCPSite(runner, host=self.host, port=self.port).start()

    async def getblock(self, blockhash: str):
        try:
            binascii.unhexlify(blockhash)
            assert len(blockhash) == 64
        except (binascii.Error, AssertionError):
            return {"error": {"code": -5, "message": "Block not found"}}
        response = await self.vo_service.getblock(blockhash)
        if not response:
            return {"error": {"code": -5, "message": "Block not found"}}
        return response

    async def getrawtransaction(self, txid: str, verbose=False):
        try:
            binascii.unhexlify(txid)
        except (binascii.Error):
            return {"error": {"code": -8, "message": "parameter 1 must be hexadecimal string (not '%s')" % txid}}
        if len(txid) != 64:
            return {"error": {"code": -8, "message": "parameter 1 must be of length 64 (not '%s')" % len(txid)}}
        response = await self.vo_service.getrawtransaction(txid)
        if not response:
            return {"error": {"code": -5, "message": "No such mempool or blockchain transaction. [maybe try again]"}}
        return response

    async def getbestblockhash(self):
        return await self.vo_service.getbestblockhash()

    async def getblockcount(self):
        res = await self.vo_service.getblockcount()
        return res is not None and str(res)

    async def getblockhash(self, blockheight: int):
        try:
            int(blockheight)
        except ValueError:
            return {"error": {"code": -5, "message": "Error parsing JSON:%s" % blockheight}}
        response = await self.vo_service.getblockhash(blockheight)
        if not response:
            return {"error": {"code": -8, "message": "Block height out of range"}}
        return response

    async def getblockheader(self, blockhash: str, verbose=True):
        try:
            binascii.unhexlify(blockhash)
            assert len(blockhash) == 64
        except (binascii.Error, AssertionError):
            return {"error": {"code": -5, "message": "Block not found"}}
        response = await self.vo_service.getblockheader(blockhash, verbose=verbose)
        if not response:
            return {"error": {"code": -5, "message": "Block not found"}}
        return response

    async def estimatefee(self, blocks: int):
        try:
            int(blocks)
        except ValueError:
            return {"error": {"code": -5, "message": "Error parsing JSON:%s" % blocks}}
        response = await self.vo_service.estimatefee(blocks)
        if response is None:
            return "-1"
        return response.get("response")

    async def estimatesmartfee(self, blocks: int):
        try:
            int(blocks)
        except ValueError:
            return {"error": {"code": -5, "message": "Error parsing JSON:%s" % blocks}}
        if not 0 < int(blocks) < 1009:
            return {"error": {"code": -8, "message": "Invalid conf_target, must be between 1 - 1008"}}
        response = await self.vo_service.estimatefee(blocks)
        if response is None:
            return {"error": {"code": -8, "message": "server error: try again"}}
        return {
            "blocks": blocks,
            "feerate": response["response"]
        }

    async def getblockchaininfo(self):
        response = await self.vo_service.getblockchaininfo()
        if response is None:
            return {"error": {"code": -8, "message": "server error: try again"}}
        return response

    async def gettxout(self, txid: str, index: int):
        response = await self.vo_service.gettxout(txid, index)
        if not response:
            return {"error": {"code": -8, "message": "server error: try again"}}
        return response
