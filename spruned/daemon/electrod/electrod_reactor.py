import asyncio
from typing import Dict
from connectrum.client import StratumClient
from spruned.application.abstracts import HeadersRepository
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon.electrod.electrod_rpc_server import ElectrodRPCServer
from spruned.daemon import database, exceptions
from spruned.application.logging_factory import Logger
from spruned.application.tools import get_nearest_parent


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
        self._sync_errors = 0

    def set_last_processed_header(self, last):
        if last != self._last_processed_header:
            self._last_processed_header = last
            Logger.electrum.info(
                'Last processed header: %s (%s)',
                self._last_processed_header and self._last_processed_header['block_height'],
                self._last_processed_header and self._last_processed_header['block_hash'],
            )

    async def on_connected(self):
        if self.store_headers:
            self.loop.create_task(self.sync_headers())
            self.rpc_server.enable_blocks_api()
        else:
            self.rpc_server.disable_blocks_api()

    async def start(self):
        self.interface.add_header_subscribe_callback(self.on_header)
        self.rpc_server.set_interface(self.interface)
        self.loop.create_task(self.interface.start(self.on_connected))
        self.loop.create_task(self.rpc_server.start())

    async def sync_headers(self):
        Logger.electrum.debug('Syncing headers, errors until now: %s' % self._sync_errors)
        if self._sync_errors > 100:
            raise exceptions.SprunedException('Too many sync errors. Suspending Sync')
        try:
            best_header_response = await self.interface.get_last_network_best_header()
            if not best_header_response:
                Logger.electrum.warning('No best header ?')
                self.loop.call_later(30, self.sync_headers())
                return

            peer, network_best_header = best_header_response
        except exceptions.NoPeersException:
            Logger.electrum.warning('Electrod is not able to find peers to sync headers. Sleeping 30 secs')
            self.loop.call_later(30, self.sync_headers())
            return

        if network_best_header and network_best_header != self._last_processed_header:
            sync = await self.on_header(peer, network_best_header)
            reschedule = 0 if not sync else 120
            self.loop.call_later(reschedule, self.sync_headers())  # loop or fallback
            Logger.electrum.debug('Rescheduling sync_headers (sync: %s) in %ss', sync, reschedule)
        else:
            reschedule = 120
            self.loop.call_later(reschedule, self.sync_headers())  # fallback (ping?)
            Logger.electrum.debug('Rescheduling sync_headers in %ss', reschedule)

    @database.atomic
    async def on_header(self, peer, network_best_header: Dict):
        assert network_best_header
        await self.lock.acquire()
        try:
            local_best_header = self.repo.get_best_header()
            if not local_best_header or local_best_header['block_height'] < network_best_header['block_height']:
                await self.on_local_headers_behind(local_best_header, network_best_header)
                return False
            elif local_best_header['block_height'] > network_best_header['block_height']:
                await self.on_network_headers_behind(local_best_header, peer=peer)
                return False

            block_hash = self.repo.get_block_hash(network_best_header['block_height'])
            if block_hash != local_best_header['block_hash']:
                raise exceptions.HeadersInconsistencyException(network_best_header)
            self.set_last_processed_header(network_best_header)
            return True
        finally:
            self.lock.release()

    @database.atomic
    async def on_local_headers_behind(self, local_best_header: Dict, network_best_header: Dict):
        chunks_at_time = 1
        try:
            if not local_best_header:
                # No local best header? This comes from the db, it must be a boostrap session.
                headers = await self.interface.get_headers_in_range_from_chunks(0, chunks_at_time)
                if not headers:
                    await asyncio.sleep(3)
                    Logger.electrum.warning(
                        'Missing headers on <on_local_headers_behind> chunks: 0, %s', chunks_at_time
                    )
                    return
                saved_headers = headers and self.repo.save_headers(headers)
                self.set_last_processed_header(saved_headers and saved_headers[-1])
            elif local_best_header['block_height'] == network_best_header['block_height'] - 1:
                # A new header is found, download again from multiple peers to verify it.
                header = await self.interface.get_header(
                    network_best_header['block_height'],
                    force_peers=len(self.interface.get_all_connected_peers()) // 2
                )
                if not header:
                    # Other peers doesn't have it yet, sleep 3 seconds, we'll try again later.
                    await asyncio.sleep(3)
                    return
                if header['block_hash'] != network_best_header['block_hash']:
                    raise exceptions.HeadersInconsistencyException(
                        'New header differs from the network at the same height'
                    )

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
                    local_best_header['block_height'],
                    network_best_header['block_height'],
                    force_peers=len(self.interface.get_all_connected_peers()) // 2
                )
                if not headers:
                    Logger.electrum.warning(
                        'Missing headers on <on_local_headers_behind> chunks: 0, %s', chunks_at_time
                    )
                    await asyncio.sleep(3)
                    return
                saved_headers = self.repo.save_headers(headers[1:])
                self.set_last_processed_header(saved_headers[-1])
            else:
                Logger.electrum.debug(
                    'Behind of %s blocks, fetching chunks',
                    network_best_header['block_height'] - local_best_header['block_height']
                )
                rewind_from = get_nearest_parent(local_best_header['block_height'], 2016) // 2016
                _from = rewind_from
                _to = rewind_from + 1 + chunks_at_time
                headers = await self.interface.get_headers_in_range_from_chunks(_from, _to)
                saved_headers = headers and self.repo.save_headers(headers, force=True)
                Logger.electrum.debug(
                    'Fetched %s headers (from chunk %s to chunk %s), saved %s headers',
                    len(headers), _from, _to, len(saved_headers)
                )
                self.set_last_processed_header(saved_headers and saved_headers[-1] or None)
        except exceptions.HeadersInconsistencyException:
            Logger.electrum.exception('Inconsistency!')
            self.set_last_processed_header(None)
            await self.handle_headers_inconsistency()
        except Exception:
            raise

    @database.atomic
    async def on_network_headers_behind(self, local_best_header: Dict, peer=None):
        Logger.electrum.warning('Network headers behind current, closing with peer in 3s')
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
            # FIXME. understand what's going on, maybe rollback

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
            'Headers inconsistency found, removed headers since %s. Current local: %s',
            remove_headers_since, local_best_header['block_height']
        )


def build_electrod(headers_repository, network, socket, concurrency=3) -> ElectrodReactor:
    electrod_rpc_server = ElectrodRPCServer(socket, headers_repository)
    electrod_interface = ElectrodInterface(
        network,
        concurrency=concurrency
    )
    electrod = ElectrodReactor(headers_repository, electrod_interface, electrod_rpc_server)
    return electrod
