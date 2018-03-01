import asyncio
from typing import Dict

from spruned.abstracts import HeadersRepository
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon.electrod.headers_repository import HeadersSQLiteRepository
from spruned.daemon.electrod.electrod_rpc_server import ElectrodRPCServer
from spruned import settings
from spruned.daemon import database


class ElectrodReactor:
    # FIXME - Move here the headers sync [out of the interface]
    def __init__(self, repo: HeadersRepository, interface, rpc_server, loop=None, store_headers=True):
        self.repo = repo
        self.interface = interface
        self.rpc_server = rpc_server
        self.loop = loop or asyncio.get_event_loop()
        self.store_headers = store_headers

    async def start(self):
        self.rpc_server.set_interface(self.interface)
        self.loop.create_task(self.interface.start())
        self.loop.create_task(self.rpc_server.start())
        if self.store_headers:
            self.loop.create_task(self.sync_headers())
            self.rpc_server.enable_blocks_api()
        else:
            self.rpc_server.disable_blocks_api()

    async def sync_headers(self):
        local_best_header = self.repo.get_best_header()
        network_best_header = self.interface.get_last_network_best_header()
        if not local_best_header or local_best_header['block_height'] < network_best_header['block_height']:
            await self.on_local_headers_behind(local_best_header, network_best_header)
        elif local_best_header['block_height'] > network_best_header['block_height']:
            await self.on_network_headers_behind(local_best_header, network_best_header)
        else:
            await self.ensure_headers_consistency(local_best_header, network_best_header)
            await self.ensure_headers_subscriptions()
            asyncio.sleep(5)
            self.loop.create_task(self.sync_headers())

    async def ensure_headers_subscriptions(self):
        pass

    async def on_local_headers_behind(self, local_best_header: Dict, network_best_header: Dict):
        pass

    async def on_network_headers_behind(self, local_best_header: Dict, network_best_header: Dict):
        pass

    async def ensure_headers_consistency(self, local_best_header: Dict, network_best_header: Dict):
        pass

    async def handle_headers_inconsistency(self, local_best_header: Dict, network_best_header: Dict):
        pass


def build_electrod() -> ElectrodReactor:
    headers_repository = HeadersSQLiteRepository(database.session)
    electrod_rpc_server = ElectrodRPCServer(settings.ELECTRUM_SOCKET, headers_repository)
    electrod_interface = ElectrodInterface(settings.NETWORK, connections_concurrency_ratio=2, concurrency=3)
    electrod_interface.add_headers_repository(headers_repository)
    electrod = ElectrodReactor(headers_repository, electrod_interface, electrod_rpc_server)
    return electrod


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    electrod = build_electrod()
    loop.create_task(electrod.start())
    loop.run_forever()
