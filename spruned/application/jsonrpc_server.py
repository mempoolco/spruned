import asyncio
import base64
import binascii
import gc

import re

import time
from aiohttp import web
import json
from jsonrpcserver.aio import methods
from jsonrpcserver import config, status
from jsonrpcserver.exceptions import JsonRpcServerError
from jsonrpcserver.response import ExceptionResponse

from spruned.application.exceptions import InvalidPOWException
from spruned.application.logging_factory import Logger
from spruned.application.tools import async_delayed_task
from spruned.daemon.exceptions import GenesisTransactionRequestedException
from spruned import __version__ as spruned_version
from spruned import __bitcoind_version_emulation__ as bitcoind_version

config.schema_validation = False

API_HELP = """
spruned %s, emulating bitcoind %s

== Blockchain ==
getbestblockhash
getblock "blockhash" ( verbosity )
getblockchaininfo
getblockcount
getblockhash height
getblockheader "hash" ( verbose )
gettxout "txid" n ( include_mempool )

== Rawtransactions ==
getrawtransaction "txid" ( verbose )
sendrawtransaction "hexstring" ( allowhighfees )

== Util ==
estimatefee nblocks
estimatesmartfee conf_target ("estimate_mode")

== Network ==
getpeerinfo

== Partially emulated for compatibility ==
getmempoolinfo
getchaintxstats
getmininginfo
getrawmempool


""" % (spruned_version, bitcoind_version)


class JsonRpcServerException(JsonRpcServerError):
    def __init__(self, code, message, data=None):
        super().__init__(data=data)
        self.code = code
        self.message = message
        self.http_status = status.HTTP_BAD_REQUEST


class JSONRPCServer:
    def __init__(self, host, port, username, password):
        self.username = username.encode()
        self.password = password.encode()
        self.host = host
        self.port = port
        self.vo_service = None
        self._auth = 'Basic %s' % base64.b64encode(self.username + b':' + self.password).decode()

    def set_vo_service(self, vo_service):
        self.vo_service = vo_service

    def _authenticate(self, request):
        return bool(request.headers.get('Authorization') == self._auth)

    @staticmethod
    def _json_dumps_with_fixed_float_precision(value, precision = 8):
        res = json.dumps(value)
        return re.sub('\d+e-07?\d+', lambda x: '%.*f' % (precision, float(x.group())), res)

    async def _handle(self, jsonrequest):
        if not self._authenticate(jsonrequest):
            return web.json_response({}, status=401)
        request = await jsonrequest.json()
        if isinstance(request, dict):
            response, http_status = await self._handle_request(request)
            return web.json_response(
                response,
                status=http_status,
                dumps=self._json_dumps_with_fixed_float_precision
            )
        elif isinstance(request, list):
            futures = []
            for r in request:
                futures.append(self._handle_request(r))
            responses = await asyncio.gather(*futures)
            data = [x[0] for x in responses]
            print('response: %s' % data)
            return web.Response(
                body=json.dumps(data),
                status=200,
            )

    async def _handle_request(self, request):
        result = {
            "id": request.get("id", 0),
            "result": None,
            "error": None
        }
        response = await methods.dispatch(request)
        result.update(response)
        if result['error'] and result['error']['code'] < -32:
            result['error']['code'] = -1
        return result, response.http_status

    def run(self, main_loop):
        self.main_loop = main_loop
        loop = asyncio.new_event_loop()
        loop.create_task(self.start())
        loop.run_forever()

    async def start(self):
        app = web.Application()
        app.router.add_post('/', self._handle)
        runner = web.AppRunner(app)
        await runner.setup()
        methods.add(self.echo)
        methods.add(self.help)
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
        methods.add(self.getpeerinfo)
        methods.add(self.getmempoolinfo)
        methods.add(self.getchaintxstats)
        methods.add(self.getmininginfo)
        methods.add(self.getrawmempool)
        methods.add(self.dev_memorysummary, name="dev-gc-stats")
        methods.add(self.dev_collect, name="dev-gc-collect")
        methods.add(self.stop, name="stop")
        methods.add(self.sendrawtransaction)

        return await web.TCPSite(runner, host=self.host, port=self.port).start()

    async def help(self, *args):
        return API_HELP

    async def echo(self, *args):
        return ""

    async def getpeerinfo(self):
        return await self.vo_service.getpeerinfo()

    async def getblock(self, blockhash: str, mode: int = 1):
        try:
            blockhash = blockhash.strip()
            binascii.unhexlify(blockhash)
            assert len(blockhash) == 64
        except (binascii.Error, AssertionError):
            raise JsonRpcServerException(
                code=-5,
                message="Error parsing JSON:%s" % blockhash
            )
        response = await self.vo_service.getblock(blockhash, mode)
        if not response:
            raise JsonRpcServerException(code=-5, message="Block not found")
        return response

    async def getrawtransaction(self, txid: str, verbose=False):
        try:
            txid = txid.strip()
            binascii.unhexlify(txid)
        except binascii.Error:
            raise JsonRpcServerException(
                code=-8,
                message="parameter 1 must be hexadecimal string (not '%s')" % txid
            )
        if len(txid) != 64:
            raise JsonRpcServerException(
                code=-8,
                message="parameter 1 must be of length 64 (not '%s')" % len(txid)
            )
        try:
            response = await self.vo_service.getrawtransaction(txid, verbose)
        except GenesisTransactionRequestedException:
            raise JsonRpcServerException(
                code=-5,
                message="The genesis block coinbase is not considered an ordinary transaction and cannot be retrieved"
            )
        except InvalidPOWException:
            raise JsonRpcServerException(
                code=-8,
                message="server error, try again"
            )
        if not response:
            raise JsonRpcServerException(
                code=-5,
                message="No such mempool or blockchain transaction. [maybe try again]"
            )
        return response

    async def getbestblockhash(self):
        return await self.vo_service.getbestblockhash()

    async def sendrawtransaction(self, rawtx: str):
        try:
            binascii.unhexlify(rawtx)
        except (binascii.Error, AssertionError):
            raise JsonRpcServerException(
                code=-22,
                message="TX decode failed"
            )
        return await self.vo_service.sendrawtransaction(rawtx)

    async def getblockcount(self):
        res = await self.vo_service.getblockcount()
        return res

    async def getblockhash(self, blockheight: int):
        try:
            int(blockheight)
        except ValueError:
            raise JsonRpcServerException(
                code=-5,
                message="Error parsing JSON:%s" % blockheight
            )
        response = await self.vo_service.getblockhash(blockheight)
        if not response:
            raise JsonRpcServerException(
                code=-8,
                message="Block height out of range"
            )
        return response

    async def getblockheader(self, blockhash: str, verbose=True):
        try:
            blockhash = blockhash.strip()
            binascii.unhexlify(blockhash)
            assert len(blockhash) == 64
        except (binascii.Error, AssertionError):
            raise JsonRpcServerException(
                code=-5,
                message="Error parsing JSON:%s" % blockhash
            )
        response = await self.vo_service.getblockheader(blockhash, verbose=verbose)
        if not response:
            raise JsonRpcServerException(
                code=-5,
                message="Block not found"
            )
        return response

    async def estimatefee(self, blocks: int):
        try:
            int(blocks)
        except ValueError:
            raise JsonRpcServerException(
                code=-5,
                message="Error parsing JSON:%s" % blocks
            )
        response = await self.vo_service.estimatefee(blocks)
        if response is None:
            return "-1"
        return response["average_satoshi_per_kb"]

    async def estimatesmartfee(self, blocks: int, estimate_mode=None):
        try:
            int(blocks)
        except ValueError:
            raise JsonRpcServerException(
                code=-5,
                message="Error parsing JSON:%s" % blocks
            )
        if not 0 < int(blocks) < 1009:
            raise JsonRpcServerException(
                code=-8,
                message="Invalid conf_target, must be between 1 - 1008"
            )
        response = await self.vo_service.estimatefee(blocks)
        if response is None:
            raise JsonRpcServerException(
                code=-8,
                message="server error: try again"
            )
        return {
            "blocks": blocks,
            "feerate": response["average_satoshi_per_kb"],
            "_origin": response
        }

    async def getblockchaininfo(self):
        response = await self.vo_service.getblockchaininfo()
        if response is None:
            raise JsonRpcServerException(
                code=-8,
                message="server error: try again"
            )
        return response

    async def gettxout(self, txid: str, index: int):
        try:
            txid = txid.strip()
            response = await self.vo_service.gettxout(txid, index)
        except:
            Logger.jsonrpc.error('Error in gettxout', exc_info=True)
            raise JsonRpcServerException(
                code=-8,
                message="server error: try again"
            )
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

    async def stop(self):
        loop = asyncio.get_event_loop()

        async def stop(l):
            l.stop()
        loop.create_task(async_delayed_task(stop(loop), 2))
        return None

    async def getmininginfo(self, *a, **kw):
        blocks = await self.vo_service.getblockcount()
        chain = self.vo_service.p2p.pool.context.get_network()['chain']
        return {
            "blocks": blocks,
            "chain": chain,
            "currentblocktx": 0,
            "currentblockweight": 0,
            "difficulty": 0,
            "networkhashps": 0,
            "pooledtx": 0,
            "errors": "spruned, emulating bitcoind, incomplete data"
        }

    async def getmempoolinfo(self, *a, **kw):
        return {
            "size": 0,
            "bytes": 0,
            "usage": 0,
            "maxmempool": 0,
            "mempoolminfee": 0,
            "errors": "spruned, emulating bitcoind, incomplete data"
        }

    async def getrawmempool(self, *a, **kw):
        return []

    async def getchaintxstats(self, *a, **kw):
        return {
            "time": int(time.time()),
            "txcount": 0,
            "window_block_count": 0,
            "window_tx_count": 0,
            "window_interval": 0,
            "txrate": 0,
            "errors": "spruned, emulating bitcoind, incomplete data"
        }

