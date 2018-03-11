import asyncio
from typing import Dict, Tuple

import time
from connectrum.client import StratumClient
from spruned.application.abstracts import HeadersRepository
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon import database, exceptions
from spruned.application.logging_factory import Logger
from spruned.application.tools import get_nearest_parent, async_delayed_task
from spruned.daemon.electrod.electrod_service import ElectrodService


class ElectrodReactor:
    def __init__(
            self,
            repo: HeadersRepository,
            interface: ElectrodInterface,
            loop=asyncio.get_event_loop(),
            store_headers=True,
            delayed_task=async_delayed_task,  # asyncio testing...  :/
            sleep_time_on_inconsistency=20
    ):
        self.repo = repo
        self.interface = interface
        self.loop = loop or asyncio.get_event_loop()
        self.store_headers = store_headers
        self.lock = asyncio.Lock()
        self.subscriptions = []
        self._last_processed_header = None
        self._inconsistencies = []
        self._sync_errors = 0
        self.delayed_task = delayed_task
        self.new_headers_fallback_poll_interval = 60*11
        self.synced = False
        self.sleep_time_on_inconsistency = sleep_time_on_inconsistency
        self.orphans_headers = []

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
            self.loop.create_task(self.check_headers())

    async def start(self):
        self.interface.add_header_subscribe_callback(self.on_new_header)
        self.loop.create_task(self.interface.start(self.on_connected))

    async def check_headers(self):
        if not self.synced or self.lock.locked():
            Logger.electrum.debug(
                'Fallback headers check: Not synced yet or sync locked (%s), retrying fallback headers check in 120s',
                self.lock.locked()
            )
            self.loop.create_task(self.delayed_task(self.check_headers(), 120))
            return

        if self._last_processed_header:
            since_last_header = int(time.time()) - self._last_processed_header['timestamp']
        else:
            since_last_header = 0
        if since_last_header < self.new_headers_fallback_poll_interval:
            retry_in = self.new_headers_fallback_poll_interval - since_last_header
            retry_in = retry_in > 0 and retry_in or self.new_headers_fallback_poll_interval // 2
            Logger.electrum.debug(
                'Fallback headers check: No best header or too recent header (%s), trying again in %s',
                since_last_header, retry_in
            )
            self.loop.create_task(self.delayed_task(self.check_headers(), retry_in))
            return
        Logger.electrum.debug(
            'Fallback headers check, current height: %s, errs: %s',
            self._last_processed_header and self._last_processed_header['block_height'],
            self._sync_errors
        )
        if self._sync_errors > 100:
            raise exceptions.SprunedException(
                'Fallback headers check: Too many sync errors. Suspending Sync'
            )
        try:
            best_header_response = self._last_processed_header and \
                                   await self.interface.get_header(
                                       self._last_processed_header['block_height'] + 1,
                                       fail_silent_out_of_range=True
                                   )
            if not best_header_response:
                Logger.electrum.debug(
                    'Fallback headers check: Looks like current header (%s) is best header',
                    self._last_processed_header['block_height']
                )
                self.loop.create_task(self.delayed_task(self.check_headers(), self.new_headers_fallback_poll_interval))
                return

            peer, network_best_header = best_header_response
        except exceptions.NoPeersException:
            Logger.electrum.warning(
                'Fallback headers check: Electrod is not able to find peers to sync headers. Sleeping 30 secs'
            )
            self.loop.create_task(self.delayed_task(self.check_headers(), 30))
            return

        if network_best_header and network_best_header != self._last_processed_header:
            sync = await self.on_new_header(peer, network_best_header)
            reschedule = 0 if not sync else self.new_headers_fallback_poll_interval
            self.loop.create_task(self.delayed_task(self.check_headers(), reschedule))  # loop or fallback
            Logger.electrum.debug('Fallback headers check: Rescheduling sync_headers (sync: %s) in %ss',
                                  sync, reschedule)
        else:
            reschedule = self.new_headers_fallback_poll_interval
            self.loop.create_task(self.delayed_task(self.check_headers(), reschedule))  # fallback (ping?)
            Logger.electrum.debug('Fallback headers check: Rescheduling sync_headers in %ss', reschedule)

    async def on_new_header(self, peer, network_best_header: Dict, _r=0):
        if not network_best_header:
            Logger.electrum.warning('Weird. No best header received on call')
            return
        if not _r:
            await self.lock.acquire()
        try:
            if self._last_processed_header and \
                    self._last_processed_header['block_hash'] == network_best_header['block_hash'] and \
                    self._last_processed_header['block_height'] == network_best_header['block_height']:
                self.synced = True
                return
            local_best_header = self.repo.get_best_header()
            if not local_best_header or local_best_header['block_height'] < network_best_header['block_height']:
                self.synced = False
                await self.on_local_headers_behind(local_best_header, network_best_header)
                return
            elif local_best_header['block_height'] > network_best_header['block_height']:
                await self.on_network_headers_behind(network_best_header, peer=peer)
                return
            block_hash = self.repo.get_block_hash(network_best_header['block_height'])
            if block_hash and block_hash != network_best_header['block_hash']:
                self.interface.handle_peer_error(peer)
                Logger.electrum.error('Inconsistency error with peer %s: (%s), %s',
                                      peer.server_info, network_best_header, block_hash
                                      )
                await asyncio.sleep(self.sleep_time_on_inconsistency)
                if not await self.on_inconsistent_header_received(peer, network_best_header, block_hash):
                    return
            self.set_last_processed_header(network_best_header)
            self.synced = True

        except (exceptions.NoHeadersException, exceptions.NoPeersException):
            self._sync_errors += 1
            if _r < 3:
                return await self.on_new_header(peer, network_best_header, _r + 1)
        finally:
            if not _r:
                self.lock.release()

    @database.atomic
    async def on_inconsistent_header_received(self, peer: StratumClient, received_header: Dict, local_hash: str):
        """
        received an inconsistent header, this network header differs for hash from
        one at the same height saved in the db.
        check which one we should trust
        """
        response = await self.interface.get_header(received_header['block_height'], fail_silent_out_of_range=True)
        if not response:
            return
        if response['block_hash'] == local_hash:
            Logger.electrum.warning('Received a controversial header (%s), handling error with peer %s',
                                    received_header, peer.server_info)
            self.interface.handle_peer_error(peer)
            return True

        elif response['block_hash'] == received_header['block_hash']:
            Logger.electrum.error('Remote peers agree the new header is ok, and our is orphan. rolling back')
            orphaned = self.repo.remove_header_at_height(received_header['block_height'])
            await self.on_new_orphan(orphaned)
            self.synced = False
            return

        else:
            Logger.electrum.error(
                'Another inconsistency (net: %s, fetched: %s, local_hash: %s, something must be _very_ wrong',
                received_header, response, local_hash
            )
            self.synced = False
            self.interface.handle_peer_error(peer)

    @database.atomic
    async def on_new_orphan(self, header: Dict):
        """
        TODO: mark header as orphan
        """
        self.orphans_headers.append(header)
        Logger.electrum.debug('Header %s orphaned, orphans: %s', header['block_hash'], self.orphans_headers)

    @database.atomic
    async def on_local_headers_behind(self, local_best_header: Dict, network_best_header: Dict):
        MAX_SINGLE_HEADERS_BEFORE_USING_CHUNKS = 10

        chunks_at_time = 1
        try:
            if not local_best_header or \
                    local_best_header['block_height'] < network_best_header['block_height'] - \
                    MAX_SINGLE_HEADERS_BEFORE_USING_CHUNKS:
                """
                bootstrap or behind of more than <N> headers
                """
                await self._fetch_headers_chunks(chunks_at_time, local_best_header, network_best_header)
            elif local_best_header['block_height'] == network_best_header['block_height'] - 1:
                """
                behind of 1 header
                """
                await self._fetch_header(network_best_header)
            else:
                """
                behind of less than MAX_SINGLE_HEADERS_BEFORE_USING_CHUNKS, download single headers and don't use chunks
                """
                await self._fetch_multiple_headers(local_best_header, network_best_header)
        except exceptions.HeadersInconsistencyException:
            Logger.electrum.error('Inconsistency error, rolling back')
            self.set_last_processed_header(None)
            await self.handle_headers_inconsistency()
            return
        except exceptions.NoPeersException as e:
            Logger.electrum.warning('Not enough peers to fetch data: %s', e)
            await asyncio.sleep(3)
            raise

    async def _fetch_multiple_headers(self, local_best_header: Dict, network_best_header: Dict):
        # The last saved header is old! It must be a while since the last time spruned synced.
        # Download the headers with a chunk, instead of tons of calls to servers..
        headers = await self.interface.get_headers_in_range(
            local_best_header['block_height'],
            network_best_header['block_height'],
        )
        if not headers:
            Logger.electrum.warning('Missing headers on <on_local_headers_behind>')
            await asyncio.sleep(3)
            raise exceptions.NoHeadersException
        saved_headers = self.repo.save_headers(headers[1:])
        self.set_last_processed_header(saved_headers[-1])

    async def _fetch_header(self, network_best_header: Dict):
        # A new header is found, download again from multiple peers to verify it.
        Logger.electrum.debug('Fetching headers')
        i = 0
        while 1:
            await asyncio.sleep(5)  # reduce race conditions and peers annoying
            # fixme - verify pow, disable multi headers fetch.
            header = await self.interface.get_header(
                network_best_header['block_height'],
                fail_silent_out_of_range=True
            )
            if header:
                break
            # Other peers doesn't have it yet, sleep 10 seconds, we'll try again later.
            await asyncio.sleep(10)
            Logger.electrum.warning('Header fetch failed')
            if i > 3:
                return
            i += 1
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
        self.synced = True

    async def _fetch_headers_chunks(self, chunks_at_time, local_best_header, network_best_header):
        """
        fetch chunks from local height to network best height, download <chunks_at_time> (>1 is unstable)
        """
        i = 0
        current_height = local_best_header and local_best_header['block_height'] or 0
        while 1:
            Logger.electrum.debug(
                'Behind of %s blocks, fetching chunks',
                network_best_header['block_height'] - current_height

            )
            local_best_height = local_best_header and local_best_header['block_height'] or 0
            rewind_from = get_nearest_parent(local_best_height, 2016) // 2016 + i
            _from = rewind_from
            _to = rewind_from + chunks_at_time
            if _from > (network_best_header['block_height'] // 2016):
                self.synced = True
                return
            headers = await self.interface.get_headers_in_range_from_chunks(_from, _to)
            if not headers:
                raise exceptions.NoHeadersException
            saving_headers = [h for h in headers if h['block_height'] > local_best_height]
            saved_headers = headers and self.repo.save_headers(saving_headers)
            Logger.electrum.debug(
                'Fetched %s headers (from chunk %s to chunk %s), saved %s headers of %s',
                len(headers), _from, _to, len(saved_headers), len(saving_headers)
            )
            self.set_last_processed_header(saved_headers and saved_headers[-1] or None)
            current_height = self._last_processed_header['block_height']
            i += 1

    @database.atomic
    async def on_network_headers_behind(self, network_best_header: Dict, peer=None):
        Logger.electrum.warning('Network headers behind current, closing with peer in 3s')
        await asyncio.sleep(3)
        await self.ensure_consistency(network_best_header, peer)

    async def ensure_consistency(self, network_best_header: Dict, peer: StratumClient):
        repo_header = self.repo.get_header_at_height(network_best_header['block_height'])
        if repo_header['block_hash'] != network_best_header['block_hash']:
            Logger.electrum.error(
                'Warning! A peer (%s), behind in height, '
                'have an header (%s) which differ from our, '
                'saved in the db: %s',
                str(peer.server_info), network_best_header, repo_header
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


def build_electrod(headers_repository, network, concurrency) -> Tuple[ElectrodReactor, ElectrodService]:
    electrod_interface = ElectrodInterface(
        network,
        concurrency=concurrency
    )
    electrod = ElectrodReactor(headers_repository, electrod_interface)
    electrod_service = ElectrodService(electrod_interface)
    return electrod, electrod_service
