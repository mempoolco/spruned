import asyncio
from typing import Dict

from spruned.abstracts import HeadersRepository
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon.electrod.headers_repository import HeadersSQLiteRepository
from spruned.daemon.electrod.electrod_rpc_server import ElectrodRPCServer
from spruned import settings
from spruned.daemon import database, exceptions
from spruned.logging_factory import Logger
from spruned.tools import get_nearest_parent, async_delayed_task


class ElectrodReactor:
    def __init__(self, repo: HeadersRepository, interface, rpc_server, loop=None, store_headers=True):
        self.repo = repo
        self.interface = interface
        self.rpc_server = rpc_server
        self.loop = loop or asyncio.get_event_loop()
        self.store_headers = store_headers
        self.lock = asyncio.Lock()
        self.subscriptions = []
        self._last_processed_header = None

    async def on_connected(self):
        if self.store_headers:
            self.loop.create_task(self.sync_headers())
            self.rpc_server.enable_blocks_api()
        else:
            self.rpc_server.disable_blocks_api()

    async def start(self):
        self.rpc_server.set_interface(self.interface)
        self.loop.create_task(self.interface.start(self.on_connected))
        self.loop.create_task(self.rpc_server.start())

    async def sync_headers(self):
        network_best_header = await self.interface.get_last_network_best_header()
        if network_best_header:
            await self.on_header(network_best_header)
        else:
            self.loop.create_task(async_delayed_task(self.sync_headers(), 30))

    @database.atomic
    async def on_header(self, network_best_header: Dict):
        if not network_best_header or network_best_header == self._last_processed_header:
            return
        await self.lock.acquire()
        try:
            local_best_header = self.repo.get_best_header()
            if not local_best_header or local_best_header['block_height'] < network_best_header['block_height']:
                await self.on_local_headers_behind(local_best_header, network_best_header)
                self.loop.create_task(self.sync_headers())

            elif local_best_header['block_height'] > network_best_header['block_height']:
                await self.on_network_headers_behind(local_best_header)
                self.loop.create_task(async_delayed_task(self.sync_headers(), 30))

            else:
                await self.ensure_headers_consistency(local_best_header)
                await self.ensure_headers_subscriptions()
                self.loop.create_task(async_delayed_task(self.sync_headers(), 30))
        finally:
            self.lock.release()

    async def ensure_headers_subscriptions(self):
        async def subscribe(peer, callback):
            await self.interface.subscribe_new_headers(peer, callback)

        peers = await self.interface.get_all_connected_peers()
        self.subscriptions = [subscription for subscription in self.subscriptions if subscription in peers]
        _ = [await subscribe(peer, self.on_header) for peer in peers if peer not in self.subscriptions]

    @database.atomic
    async def on_local_headers_behind(self, local_best_header: Dict, network_best_header: Dict):
        print('on local headers behind: %s - %s' % (local_best_header['block_height'], network_best_header['block_height']))
        try:
            if not local_best_header:
                headers = await self.interface.get_headers_from_chunk(0)
                saved_headers = headers and self.repo.save_headers(headers)
                self._last_processed_header = saved_headers and saved_headers[-1]

            if local_best_header['block_height'] == network_best_header['block_height'] - 1:
                self.repo.save_header(
                    network_best_header['block_hash'],
                    network_best_header['block_height'],
                    network_best_header['header_bytes'],
                    network_best_header['prev_block_hash']
                )
                self._last_processed_header = network_best_header
            elif local_best_header['block_height'] > network_best_header['block_height'] - 30:
                headers = await self.interface.get_headers_in_range(
                    local_best_header['block_height'], network_best_header['block_height']
                )
                saved_headers = self.repo.save_headers(headers[1:])
                self._last_processed_header = saved_headers[-1]
            else:
                rewind_from = (get_nearest_parent(local_best_header['block_height'], 2016) / 2016)
                headers = await self.interface.get_headers_from_chunk(rewind_from + 1)
                saved_headers = headers and self.repo.save_headers(headers, force=True)
                self._last_processed_header = saved_headers and saved_headers[-1]
        except exceptions.HeadersInconsistencyException:
            self._last_processed_header = None
            await self.handle_headers_inconsistency()

    @database.atomic
    async def on_network_headers_behind(self, local_best_header: Dict):
        Logger.electrum.warning('Network headers behind current, ensuring consistency')
        await self.ensure_headers_consistency(local_best_header)

    @database.atomic
    async def ensure_headers_consistency(self, local_best_header: Dict):
        check_from_height = get_nearest_parent(local_best_header['block_height'] - 2016*4, 2016)
        chunk_index = check_from_height // 2016
        local_headers = self.repo.get_headers_since_height(check_from_height)
        network_headers = await self.interface.get_headers_from_chunk(chunk_index)
        try:
            for i, header in enumerate(local_headers):
                assert header[i]['block_height'] == network_headers[i]['block_height']
                if header[i]['block_hash'] != network_headers[i]['block_hash']:
                    raise exceptions.HeadersInconsistencyException()
        except exceptions.HeadersInconsistencyException:
            Logger.electrum.exception()
            await self.handle_headers_inconsistency()

    @database.atomic
    async def handle_headers_inconsistency(self):
        self._last_processed_header = None
        local_best_header = self.repo.get_best_header()
        remove_headers_since = get_nearest_parent(local_best_header['block_height'], 2016)
        self.repo.remove_headers_after_height(remove_headers_since)
        Logger.electrum.warning(
            'Headers inconsistency found, removed headers since %s. Current local: %s' % (
                remove_headers_since, local_best_header['block_height']
            )
        )


def build_electrod() -> ElectrodReactor:
    headers_repository = HeadersSQLiteRepository(database.session)
    electrod_rpc_server = ElectrodRPCServer(settings.ELECTRUM_SOCKET, headers_repository)
    electrod_interface = ElectrodInterface(settings.NETWORK, connections_concurrency_ratio=2, concurrency=3)
    electrod = ElectrodReactor(headers_repository, electrod_interface, electrod_rpc_server)
    return electrod


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    electrod = build_electrod()
    loop.create_task(electrod.start())
    loop.run_forever()
