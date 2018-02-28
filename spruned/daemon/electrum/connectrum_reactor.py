import asyncio
from aiohttp import web
from aiohttp.web import Response
from spruned.abstracts import HeadersRepository
from spruned.daemon.electrum.connectrum_interface import ConnectrumInterface
from spruned.daemon.electrum.headers_repository import HeadersSQLiteRepository
from spruned import settings
from spruned.daemon import database


class ConnectrumReactor:
    def __init__(self, repo: HeadersRepository, connectrum_interface, app):
        self.app = app
        self.repo = repo
        self.connectrum_interface = connectrum_interface
        self.set_routes()

    def set_routes(self):
        self.app.router.add_route('GET', '/getrawtransaction/{txid}', self._getrawtransaction)
        """
        self.app.router.add_route('POST', '/sendrawtransaction', self._sendrawtransaction)
        if self.headers_repository:
            self.app.router.add_route('GET', '/getblockheaderatheight/{blockheight}', self._getblockheaderatheight)
            self.app.router.add_route('GET', '/getblockheaderforhash/{blockhash}', self._getblockheaderforhash)
        """

    def start(self):
        self.app.loop.create_task(self.connectrum_interface.start())
        web.run_app(self.app, host='localhost', port='16108')

    async def _getrawtransaction(self, request):
        txid = request.match_info['txid']
        responses = await self.connectrum_interface.getrawtransaction(txid)
        for response in responses:
            if len(responses) == 1 or responses.count(response) > len(responses) / 2 + .1:
                return Response(status=200, text=response, content_type='application/json')
        return Response(status=502, text='No quorum', content_type='text/html')

    async def _getblockheaderatheight(self, blockheight):
        pass

    async def _getblockheaderforhash(self, blockhash):
        pass

    async def _sendrawtransaction(self, rawtransaction):
        pass


if __name__ == '__main__':
    headers_repository = HeadersSQLiteRepository(database.session)
    app = web.Application(loop=asyncio.get_event_loop())
    interface = ConnectrumInterface(settings.NETWORK, app, connections_concurrency_ratio=5)
    interface.add_headers_repository(headers_repository)
    reactor = ConnectrumReactor(headers_repository, interface, app)
    reactor.start()
