import asyncio
from typing import Dict
from connectrum.client import StratumClient
from spruned.application.abstracts import HeadersRepository
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon.electrod.electrod_rpc_server import ElectrodRPCServer
from spruned.daemon import database, exceptions
from spruned.application.logging_factory import Logger
from spruned.application.tools import get_nearest_parent, async_delayed_task


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
        self._inconsistencies = []

    def set_last_processed_header(self, last):
        if last != self._last_processed_header:
            self._last_processed_header = last
            Logger.electrum.debug(
                'Last processed header: %s (%s)',
                self._last_processed_header and self._last_processed_header['block_height'],
                self._last_processed_header and self._last_processed_header['block_hash'],
            )

    async def on_connected(self):
        Logger.electrum.info(
            'Electrum interface connected to %s peers' % len(await self.interface.get_all_connected_peers())
        )
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
        peer, network_best_header = await self.interface.get_last_network_best_header()
        if network_best_header and network_best_header != self._last_processed_header:
            sync = await self.on_header(peer, network_best_header)
            self.loop.create_task(async_delayed_task(self.sync_headers(), sync and 30 or 0))
        else:
            self.loop.create_task(async_delayed_task(self.sync_headers(), 30))

    @database.atomic
    async def on_header(self, peer, network_best_header: Dict):
        assert network_best_header
        await self.lock.acquire()
        try:
            local_best_header = self.repo.get_best_header()
            if not local_best_header or local_best_header['block_height'] < network_best_header['block_height']:
                await self.on_local_headers_behind(local_best_header, network_best_header)
                self.loop.create_task(self.sync_headers())
                return
            elif local_best_header['block_height'] > network_best_header['block_height']:
                await self.on_network_headers_behind(local_best_header, peer=peer)
                return
            blockhash = self.repo.get_block_hash(network_best_header['block_height'])
            if blockhash != local_best_header['block_hash']:
                raise exceptions.HeadersInconsistencyException(network_best_header)
            self.set_last_processed_header(network_best_header)
            return True
        finally:
            await self.ensure_headers_subscriptions()
            self.lock.release()

    async def ensure_headers_subscriptions(self):
        peers = await self.interface.get_all_connected_peers()
        self.subscriptions = [subscription for subscription in self.subscriptions if subscription in peers]
        for peer in peers:
            if peer not in self.subscriptions:
                Logger.electrum.debug('Subscribing to %s' % peer)
                self.loop.create_task(self.interface.subscribe_new_headers(peer, self.on_header))
                self.subscriptions.append(peer)
        return

    @database.atomic
    async def on_local_headers_behind(self, local_best_header: Dict, network_best_header: Dict):
        chunks_at_time = 3
        try:
            if not local_best_header:
                # No local best header? This comes from the db, it must be a boostrap session.
                headers = await self.interface.get_headers_in_range_from_chunks(0, chunks_at_time)
                if not headers:
                    asyncio.sleep(3)
                    Logger.electrum.warning(
                        'Missing headers on <on_local_headers_behind> chunks: 0, %s' % chunks_at_time
                    )
                    return
                saved_headers = headers and self.repo.save_headers(headers)
                self.set_last_processed_header(saved_headers and saved_headers[-1])
            elif local_best_header['block_height'] == network_best_header['block_height'] - 1:
                # A new header is found, just save it atm.
                # FIXME: Verify the agreement from other peers, check 2 random peers
                self.repo.save_header(
                    network_best_header['block_hash'],
                    network_best_header['block_height'],
                    network_best_header['header_bytes'],
                    network_best_header['prev_block_hash']
                )
                self.set_last_processed_header(network_best_header)
            elif local_best_header['block_height'] > network_best_header['block_height'] - 30:
                # The last saved header is old! It must be a while since the last time spruned synced.
                # Download the headers with a chunk, instead of tons of calls to servers..
                headers = await self.interface.get_headers_in_range(
                    local_best_header['block_height'], network_best_header['block_height']
                )
                if not headers:
                    Logger.electrum.warning(
                        'Missing headers on <on_local_headers_behind> chunks: 0, %s' % chunks_at_time
                    )
                    asyncio.sleep(3)
                    return
                saved_headers = self.repo.save_headers(headers[1:])
                self.set_last_processed_header(saved_headers[-1])
            else:
                rewind_from = get_nearest_parent(local_best_header['block_height'], 2016) // 2016
                headers = await self.interface.get_headers_in_range_from_chunks(
                    rewind_from + 1, rewind_from + 1 + chunks_at_time
                )
                saved_headers = headers and self.repo.save_headers(headers, force=True)
                self.set_last_processed_header(saved_headers and saved_headers[-1])
        except exceptions.HeadersInconsistencyException:
            Logger.electrum.exception('Inconsistency!')
            self.set_last_processed_header(None)
            await self.handle_headers_inconsistency()

    @database.atomic
    async def on_network_headers_behind(self, local_best_header: Dict, peer=None):
        Logger.electrum.warning('Network headers behind current, closing with peer in 3.. 2... 1...')
        await asyncio.sleep(3)
        await self.ensure_consistency(local_best_header, peer)

    async def ensure_consistency(self, local_best_header: Dict, peer: StratumClient):
        repo_header = self.repo.get_header_at_height(local_best_header['block_height'])
        if repo_header['block_hash'] != local_best_header['block_hash']:
            Logger.electrum.error(
                'Warning! A peer (%s), behind in height, '
                'have an header which differ from our, '
                'saved in the db: %s',
                str(peer.server_info), local_best_header, repo_header
            )

        await self.interface.disconnect_from_peer(peer)
        peer.close()
        Logger.electrum.info('Closing with peer %s', str(peer.server_info))


    @database.atomic
    async def handle_headers_inconsistency(self):
        self.set_last_processed_header(None)
        local_best_header = self.repo.get_best_header()
        remove_headers_since = get_nearest_parent(local_best_header['block_height'], 2016)
        self.repo.remove_headers_after_height(remove_headers_since)
        Logger.electrum.warning(
            'Headers inconsistency found, removed headers since %s. Current local: %s' % (
                remove_headers_since, local_best_header['block_height']
            )
        )


def build_electrod(headers_repository, network, socket, concurrency=3) -> ElectrodReactor:
    electrod_rpc_server = ElectrodRPCServer(socket, headers_repository)
    electrod_interface = ElectrodInterface(
        network,
        connections_concurrency_ratio=2,
        concurrency=concurrency
    )
    electrod = ElectrodReactor(headers_repository, electrod_interface, electrod_rpc_server)
    return electrod


if __name__ == '__main__':
    from spruned.application import settings
    loop = asyncio.get_event_loop()
    electrod = build_electrod(settings.NETWORK, settings.ELECTROD_SOCKET, settings.ELECTROD_CONCURRENCY)
    loop.create_task(electrod.start())
    loop.run_forever()
