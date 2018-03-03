import asyncio
import aiomas
from spruned.application import settings
from spruned.application.abstracts import RPCAPIService


class ElectrodService(RPCAPIService):
    def __init__(self, socketfile):
        self.socketfile = socketfile

    async def call(self, method, callback, payload):
        rpc_con = await aiomas.rpc.open_connection(self.socketfile)
        call = getattr(rpc_con.remote, method)
        resp = await call(payload)
        await rpc_con.close()
        callback and callback(resp)
        return resp

    def _async_to_sync_call(self, method, payload):
        """
        not so efficient
        """
        res = []
        def cb(resp, res):
            res.append(resp)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(self.call(method, lambda x: cb(x, res), payload))
        return res and res[0]

    def getrawtransaction(self, txid, verbose=False):
        payload = {"txid": txid, "verbose": verbose}
        return self._async_to_sync_call("getrawtransaction", payload)

    def getblockheader(self, blockhash, verbose=True):
        payload = {"block_hash": blockhash, "verbose": verbose}
        return self._async_to_sync_call("getblockheader", payload)

    def getblock(self, txid, verbose=False):
        return None

    def getblockhash(self, height: int):
        payload = {"block_height": height}
        return self._async_to_sync_call("getblockhash", payload)

    def getblockheight(self, blockhash: str):
        payload = {"block_hash": blockhash}
        return self._async_to_sync_call("getblockheight", payload)

    def estimatefee(self, blocks: int):
        payload = {"blocks": blocks}
        return self._async_to_sync_call("estimatefee", payload)

    def sendrawtransaction(self, rawtx: str):
        payload = {"rawtx": rawtx}
        return self._async_to_sync_call("sendrawtransaction", payload)

    @property
    def available(self) -> bool:
        return True


if __name__ == '__main__':
    client = ElectrodService(settings.ELECTRUM_SOCKET)
    rawtx = client.getrawtransaction('5029394b46e48dfdcf2eaf0bbaad97735a7fa44f2cf51007aa69584c2476fb27')
    print(rawtx)
    blockheader = client.getblockheader('0000000000000000001d5797e770b7f9c4bd8db8aed4b4b649b50402acd1bb7a')
    print(blockheader)

