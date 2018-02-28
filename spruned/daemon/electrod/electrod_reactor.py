import asyncio
from typing import Tuple
from spruned.abstracts import HeadersRepository
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon.electrod.headers_repository import HeadersSQLiteRepository
from spruned import settings
from spruned.daemon import database
import aiomas


class ElectrodReactor:
    def __init__(self, repo: HeadersRepository, interface, rpc_server, loop=None):
        self.repo = repo
        self.interface = interface
        self.rpc_server = rpc_server
        self.loop = loop or asyncio.get_event_loop()

    async def start(self):
        self.rpc_server.set_interface(self.interface)
        self.loop.create_task(self.interface.start())
        self.loop.create_task(self.rpc_server.start())


class ElectrodRPCServer:
    router = aiomas.rpc.Service()

    def __init__(self, endpoint: (str, Tuple)):
        self.endpoint = endpoint
        self.interface: ElectrodInterface = None

    def set_interface(self, interface: ElectrodInterface):
        assert not self.interface, "RPC Server already initialized"
        self.interface = interface

    async def start(self):
        return await aiomas.rpc.start_server(self.endpoint, self)

    @router.expose
    async def getrawtransaction(self, txid: str, verbose=False):
        return await self.interface.getrawtransaction(txid)


def build_electrod() -> ElectrodReactor:
    headers_repository = HeadersSQLiteRepository(database.session)
    electrod_rpc_server = ElectrodRPCServer(settings.ELECTRUM_SOCKET)
    electrod_interface = ElectrodInterface(settings.NETWORK, connections_concurrency_ratio=5, concurrency=1)
    electrod_interface.add_headers_repository(headers_repository)
    electrod = ElectrodReactor(headers_repository, electrod_interface, electrod_rpc_server)
    return electrod


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    electrod = build_electrod()
    loop.create_task(electrod.start())
    loop.run_forever()
