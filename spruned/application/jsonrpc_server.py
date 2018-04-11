import binascii
import gc
from aiohttp import web
from jsonrpcserver.aio import methods
from jsonrpcserver import config
from jsonrpcserver.response import ExceptionResponse

from spruned.application.logging_factory import Logger

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
        elif isinstance(response, dict):
            if response.get("result", None) is None:
                return web.Response(body=response, status=200)
            if isinstance(response["result"], dict) and "error" in response["result"]:
                Logger.jsonrpc.error('Error in response: %s', response)
                r = {'error': None}
                response.update(response['result'])
                return web.json_response(r, status=400)
            return web.json_response(response)
        return web.json_response(body=response, status=200)

    async def start(self):
        app = web.Application()
        app.router.add_post('/', self._handle)
        runner = web.AppRunner(app)
        await runner.setup()
        methods.add(self.echo)
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
        methods.add(self.dev_memorysummary, name="dev-gc-stats")
        methods.add(self.dev_collect, name="dev-gc-collect")

        return await web.TCPSite(runner, host=self.host, port=self.port).start()

    async def echo(self, *args):
        return ""

    async def getblock(self, blockhash: str, mode: int = 1):
        try:
            blockhash = blockhash.strip()
            binascii.unhexlify(blockhash)
            assert len(blockhash) == 64
        except (binascii.Error, AssertionError):
            return {"error": {"code": -5, "message": "Block not found"}}
        response = await self.vo_service.getblock(blockhash, mode)
        if not response:
            return {"error": {"code": -5, "message": "Block not found"}}
        return response

    async def getrawtransaction(self, txid: str, verbose=False):
        try:
            txid = txid.strip()
            binascii.unhexlify(txid)
        except (binascii.Error):
            return {"error": {"code": -8, "message": "parameter 1 must be hexadecimal string (not '%s')" % txid}}
        if len(txid) != 64:
            return {"error": {"code": -8, "message": "parameter 1 must be of length 64 (not '%s')" % len(txid)}}
        response = await self.vo_service.getrawtransaction(txid, verbose)
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
            blockhash = blockhash.strip()
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
        return response

    async def estimatesmartfee(self, blocks: int, estimate_mode=None):
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
            "feerate": response,
            "_feerate": "{:.8f}".format(response)
        }

    async def getblockchaininfo(self):
        response = await self.vo_service.getblockchaininfo()
        if response is None:
            return {"error": {"code": -8, "message": "server error: try again"}}
        return response

    async def gettxout(self, txid: str, index: int):
        try:
            txid = txid.strip()
            response = await self.vo_service.gettxout(txid, index)
        except:
            Logger.jsonrpc.error('Error in gettxout', exc_info=True)
            return {"error": {"code": -8, "message": "server error: try again"}}
        return response

    async def dev_memorysummary(self):
        return {"stats": gc.get_stats()}

    async def dev_collect(self):
        res = {
            "before": gc.get_stats()
        }
        gc.collect()
        res['after'] = gc.get_stats()
        return res
