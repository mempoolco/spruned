import asyncio
from typing import Dict
import time
from spruned.application.abstracts import HeadersRepository
from spruned.daemon.electrod.electrod_connection import ElectrodConnection
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon import exceptions
from spruned.application import database
from spruned.application.logging_factory import Logger
from spruned.application.tools import get_nearest_parent, async_delayed_task


class HeadersReactor:
    """
    This reactor keeps headers aligned to the best height.
    Designed to work with the Electrum Network, it may be ported easily to P2P
    """
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
        self.on_best_height_hit_volatile_callbacks = []
        self.on_best_height_hit_persistent_callbacks = []
        self._on_new_best_header_callbacks = []

    def add_on_new_header_callback(self, callback):
        self._on_new_best_header_callbacks.append(callback)

    def add_on_best_height_hit_volatile_callbacks(self, callback):
        self.on_best_height_hit_volatile_callbacks.append(callback)

    def add_on_best_height_hit_persistent_callbacks(self, callback):
        self.on_best_height_hit_persistent_callbacks.append(callback)

    def set_last_processed_header(self, last):
        if last != self._last_processed_header:
            self._last_processed_header = last
            Logger.electrum.info(
                'Last processed header: %s (%s)',
                self._last_processed_header and self._last_processed_header['block_height'],
                self._last_processed_header and self._last_processed_header['block_hash'],
            )
            if self._last_processed_header:
                for callback in self._on_new_best_header_callbacks:
                    self.loop.create_task(callback(self._last_processed_header))

    async def on_connected(self):
        if self.store_headers:
            self.loop.create_task(self.check_headers())

    async def start(self):
        self.interface.add_header_subscribe_callback(self.on_new_header)
        self.interface.add_on_connected_callback(self.on_connected)
        self.loop.create_task(self.interface.start())

    async def check_headers(self):
        if not self.interface.is_pool_online:
            Logger.electrum.error(
                'Looks like there is no internet connection. check_headers delayed %s',
                self.new_headers_fallback_poll_interval
            )
            self.loop.create_task(self.delayed_task(self.check_headers(), self.new_headers_fallback_poll_interval))
            return
        if self._sync_errors >= 100:
            raise exceptions.SprunedException(
                'Fallback headers check: Too many sync errors. Suspending Sync'
            )
        if not self.synced or self.lock.locked():
            Logger.electrum.debug(
                'Fallback headers check: Not synced yet or sync locked (%s), retrying fallback headers check in 30s',
                self.lock.locked()
            )
            self.loop.create_task(self.delayed_task(self.check_headers(), 30))
            return

        since_last_header = self._last_processed_header and int(time.time()) - self._last_processed_header['timestamp']
        if int(since_last_header) < self.new_headers_fallback_poll_interval:
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
        try:
            best_header_response = self._last_processed_header and \
                                   await self.interface.get_header(
                                       self._last_processed_header['block_height'] + 1,
                                       fail_silent_out_of_range=True,
                                       get_peer=True
                                   )
            if best_header_response is None:
                Logger.electrum.debug(
                    'Fallback headers check: Looks like current header (%s) is best header',
                    self._last_processed_header and self._last_processed_header['block_height']
                )
                self.loop.create_task(self.delayed_task(self.check_headers(), self.new_headers_fallback_poll_interval))
                return
            peer, network_best_header = best_header_response
            Logger.electrum.debug('Best header obtained from peer %s: on_new_header(): %s', peer, network_best_header)
        except (
                exceptions.NoQuorumOnResponsesException,
                exceptions.NoPeersException,
                exceptions.NoHeadersException
        ):
            Logger.electrum.warning(
                'Fallback headers check: Electrod is not able to find peers to sync headers. Sleeping 30 secs'
            )
            self.loop.create_task(self.delayed_task(self.check_headers(), 30))
            return

        if network_best_header and network_best_header != self._last_processed_header:
            self.loop.create_task(self.on_new_header(peer, network_best_header))
            self.loop.create_task(self.delayed_task(self.check_headers(), 30))  # loop or fallback
            Logger.electrum.debug('Fallback headers check: Rescheduling sync_header in %ss', 30)
        else:
            self.loop.create_task(self.delayed_task(self.check_headers(), self.new_headers_fallback_poll_interval))
            Logger.electrum.debug(
                'Fallback headers check: Rescheduling sync_headers in %ss',
                self.new_headers_fallback_poll_interval
            )

    async def on_new_header(self, peer, network_best_header: Dict, retries=0):
        if not network_best_header:
            Logger.electrum.warning('Weird. No best header received on call')
            return
        try:
            not retries and await self.lock.acquire()
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
                await self.interface.handle_peer_error(peer)
                Logger.electrum.error('Inconsistency error with peer %s: (%s), %s',
                                      peer.server_info, network_best_header, block_hash
                                      )
                await asyncio.sleep(self.sleep_time_on_inconsistency)
                if not await self.on_inconsistent_header_received(peer, network_best_header, block_hash):
                    return
            self.set_last_processed_header(network_best_header)
            self.synced = True
        except (
                exceptions.NoQuorumOnResponsesException,
                exceptions.NoPeersException,
                exceptions.NoHeadersException,
        ) as e:
            self._sync_errors += 1
            if retries < 5:
                return await self.on_new_header(peer, network_best_header, retries + 1)
            Logger.electrum.error('Excessive recursion on new_header. %s', e)
        finally:
            if self.synced:
                if self.on_best_height_hit_volatile_callbacks:
                    while 1:
                        if not self.on_best_height_hit_volatile_callbacks:
                            break
                        callback = self.on_best_height_hit_volatile_callbacks.pop(0) or None
                        self.loop.create_task(callback(self._last_processed_header))
                for callback in self.on_best_height_hit_persistent_callbacks:
                    self.loop.create_task(callback(self._last_processed_header))

            not retries and self.lock.release()

    @database.atomic
    async def on_inconsistent_header_received(self, peer: ElectrodConnection, received_header: Dict, local_hash: str):
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
                                    received_header, peer.version)
            await self.interface.handle_peer_error(peer)
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
            await self.interface.handle_peer_error(peer)

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
                bootstrap or behind more than <N> headers
                """
                await self._fetch_headers_chunks(chunks_at_time, local_best_header, network_best_header)
            elif local_best_header['block_height'] == network_best_header['block_height'] - 1:
                """
                behind 1 header
                """
                await self._save_header(network_best_header)
            else:
                """
                behind less than MAX_SINGLE_HEADERS_BEFORE_USING_CHUNKS, download single headers and don't use chunks
                """
                await self._fetch_multiple_headers(local_best_header, network_best_header)
        except exceptions.HeadersInconsistencyException:
            Logger.electrum.error('Inconsistency error, rolling back')
            self.set_last_processed_header(None)
            await self.handle_headers_inconsistency()
            return

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
        self.synced = True

    async def _save_header(self, network_best_header: Dict):
        # A new header is found, download again from multiple peers to verify it.
        Logger.electrum.debug('Fetching headers')
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
        saving_headers = []
        while 1:
            Logger.electrum.debug(
                '%s headers behind, downloading',
                network_best_header['block_height'] - current_height - len(saving_headers)

            )
            local_best_height = local_best_header and local_best_header['block_height'] or 0
            rewind_from = get_nearest_parent(local_best_height, 2016) // 2016 + i
            _from = rewind_from
            _to = rewind_from + chunks_at_time
            if _from > (network_best_header['block_height'] // 2016):
                saved_headers = saving_headers and self.repo.save_headers(saving_headers) or []
                saved_headers and self.set_last_processed_header(saved_headers[-1])

                self.synced = True
                return
            res = await self.interface.get_headers_in_range_from_chunks(_from, _to, get_peer=True)
            peer, headers = res if res else (None, [])
            if not headers:
                raise exceptions.NoHeadersException
            if local_best_height:
                saving_headers = saving_headers + [h for h in headers if h['block_height'] > local_best_height]
            else:
                saving_headers = saving_headers + headers
            try:
                if not i % 5:
                    saved_headers = headers and self.repo.save_headers(saving_headers) or []
                    saving_headers = []
                else:
                    saved_headers = []

            except exceptions.HeadersInconsistencyException:
                await peer.disconnect()
                raise
            Logger.electrum.debug(
                'Fetched %s headers (chunk %s/%s), tot. %s',
                len(headers), _from, _to, len(saving_headers)
            )
            if saved_headers:
                self.set_last_processed_header(saved_headers[-1])
                current_height = self._last_processed_header['block_height']
            elif saving_headers:
                self.set_last_processed_header(None)
            i += 1

    @database.atomic
    async def on_network_headers_behind(self, network_best_header: Dict, peer=None):
        Logger.electrum.warning('Network headers behind current, closing with peer in 3s')
        await asyncio.sleep(3)
        await self.ensure_consistency(network_best_header, peer)

    async def ensure_consistency(self, network_best_header: Dict, peer: ElectrodConnection):
        repo_header = self.repo.get_header_at_height(network_best_header['block_height'])
        if repo_header['block_hash'] != network_best_header['block_hash']:
            Logger.electrum.error(
                'Warning! A peer (%s), behind in height, '
                'have an header (%s) which differ from our, '
                'saved in the db: %s',
                str(peer.hostname), network_best_header, repo_header
            )
            # FIXME. understand what's going on, maybe rollback
            # TODO - This is STILL an important issue.

        await self.interface.disconnect_from_peer(peer)
        Logger.electrum.info('Closing with peer %s', str(peer.hostname))

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
