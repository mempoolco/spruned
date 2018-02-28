import asyncio
from spruned.abstracts import HeadersRepository
from spruned.daemon.electrum.connectrum_interface import ConnectrumInterface
from spruned.daemon.electrum.headers_repository import HeadersSQLiteRepository
from spruned import settings
from spruned.daemon import database
import aiomas


class ConnectrumReactor:
    def __init__(self, repo: HeadersRepository, connectrum_interface, rpc_server, loop=None):
        self.repo = repo
        self.connectrum_interface = connectrum_interface
        self.rpc_server = rpc_server
        self.loop = loop or asyncio.get_event_loop()

    def start(self):
        self.loop.create_task(self.connectrum_interface.start())
        self.loop.create_task(aiomas.rpc.start_server('/tmp/aiomas', self.rpc_server))
        self.loop.run_forever()

    async def _getrawtransaction(self, request):
        txid = request.match_info['txid']
        responses = await self.connectrum_interface.getrawtransaction(txid)
        for response in responses:
            if len(responses) == 1 or responses.count(response) > len(responses) / 2 + .1:
                pass

    async def _getblockheaderatheight(self, blockheight):
        pass

    async def _getblockheaderforhash(self, blockhash):
        pass

    async def _sendrawtransaction(self, rawtransaction):
        pass


class RPCServer:
    router = aiomas.rpc.Service()

    @router.expose
    def getrawtransaction(self, a, b):
        return a + b


if __name__ == '__main__':
    rpc_server = RPCServer()
    headers_repository = HeadersSQLiteRepository(database.session)
    interface = ConnectrumInterface(settings.NETWORK, connections_concurrency_ratio=4, concurrency=3)
    interface.add_headers_repository(headers_repository)
    reactor = ConnectrumReactor(headers_repository, interface, rpc_server)
    reactor.start()
