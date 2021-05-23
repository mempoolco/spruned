import asyncio
import typing
from spruned.application.exceptions import InvalidPOWException
from spruned.application.logging_factory import Logger
from spruned.application.tools import async_delayed_task
from spruned.application.consensus import verify_pow
from spruned.daemon import exceptions
from spruned.daemon.p2p.connection import P2PConnection
from spruned.daemon.p2p.interface import P2PInterface


class HeadersReactor:
    def __init__(
            self,
            repo,
            interface: P2PInterface,
            loop=asyncio.get_event_loop(),
            delayed_task=async_delayed_task,
            min_peers_agreement=1
    ):
        self.repo = repo
        self.interface = interface
        self.loop = loop or asyncio.get_event_loop()
        self.lock = asyncio.Lock()
        self.subscriptions = []
        self._last_processed_header = None
        self._best_chain = None
        self._sync_errors = 0
        self.delayed_task = delayed_task
        self.new_headers_fallback_poll_interval = 10
        self.synced = False
        self.on_best_height_hit_volatile_callbacks = []
        self.on_best_height_hit_persistent_callbacks = []
        self._on_new_best_header_callbacks = []
        self._available = False
        self._min_peers_agreement = min_peers_agreement
        self._fetch_headers_lock = asyncio.Lock()
        self._last_connection = None

    def add_on_new_header_callback(self, callback: callable):
        self._on_new_best_header_callbacks.append(callback)

    def set_last_processed_header(self, last: typing.Optional[typing.Dict]):
        if last != self._last_processed_header:
            self._last_processed_header = last
            Logger.electrum.info(
                'Last processed header: %s (%s)',
                self._last_processed_header and self._last_processed_header['block_height'],
                self._last_processed_header and self._last_processed_header['block_hash'],
            )
            if self._last_processed_header and self.synced:
                for callback in self._on_new_best_header_callbacks:
                    self.loop.create_task(callback(self._last_processed_header))

    async def start(self):
        best_header = self.repo.get_best_header()
        best_chain = self.repo.get_headers_since_height(best_header['block_height'] - 5)
        self._best_chain = best_chain
        self.set_last_processed_header(best_header)
        await self._fetch_headers_loop()

    async def _fetch_headers_loop(self):
        """
        keep the headers in sync.
        """
        await self._fetch_headers_lock.acquire()
        try:
            if len(self.interface.get_connections()) < self._min_peers_agreement:
                self._next_fetch_headers_schedule = self.loop.call_later(
                    5, lambda: self.loop.create_task(self._fetch_headers_loop())
                )
                return
            await self._fetch_headers()
            self._next_fetch_headers_schedule = self.loop.call_later(
                20, lambda: self.loop.create_task(self._fetch_headers_loop())
            )
        finally:
            self._fetch_headers_lock.release()

    async def _check_headers_with_best_chain(self, connection: P2PConnection, headers: typing.List):
        """
        check if headers are:
         - wanted, because probably requested
         - in sync with what we know
         - new
         - correct
        """
        wanted = self._best_chain[0]['block_hash'] == headers[0]['prev_block_hash']
        new_in_sync = self._best_chain[-1]['block_hash'] == headers[0]['prev_block_hash'] and len(headers) > 1

        if wanted and connection == self._last_connection:
            connection.add_success()  # good boy
            new_headers = await self._evaluate_wanted_headers(headers)
        elif new_in_sync:
            new_headers = headers[1:]
        else:
            # Received an header that it is not in sync with what we know, nor we have requested it.
            # Could be anything. Discard it at the moment.
            new_headers = None
        return new_headers

    async def _evaluate_wanted_headers(self, headers) -> typing.Optional[typing.List]:
        if any(
            filter(
                lambda h: str(h[0]['prev_block_hash']) != h[1]['block_hash'],
                zip(headers, self._best_chain)
            )
        ):
            raise exceptions.HeadersInconsistencyException(headers)
        if len(headers) < len(self._best_chain):
            return None  # we are ahead
        elif len(headers) == len(self._best_chain):
            return None  # we are even
        else:
            return headers[len(self._best_chain) - 1:]

    async def _evaluate_consensus_for_new_headers(self, headers: typing.List):
        """
        ensure:
        - chain-link is ok
        - pow is ok
        - difficulty is ok
        """
        for i, h in enumerate(headers):
            if not i:
                prev_hash = self._best_chain[-1]['block_hash']
                block_height = self._best_chain[-1]['block_height'] + 1
            else:
                prev_hash = headers[i-1]['block_hash']
                block_height = headers[i-1]['block_height']
            if prev_hash != h['prev_block_hash']:
                raise exceptions.ChainBrokenException(
                    '%s != %s', prev_hash, h['prev_block_hash']
                )
            try:
                verify_pow(h['header_bytes'], bytes.fromhex(h['block_hash']))
            except InvalidPOWException:
                raise exceptions.InvalidHeaderProofException
            headers[i]['block_height'] = block_height
            # todo difficulty check

    async def _save_new_headers(self, headers: typing.List):
        self.repo.save_headers(headers)
        for h in headers[-6:]:
            new = {
                'block_hash': h['block_hash'],
                'block_height': self._last_processed_header['block_height'] + 1
            }
            self._last_processed_header = new
            self._best_chain.append(new)
            self._best_chain.pop(0)

    async def on_headers(self, connection: P2PConnection, headers: typing.List):  # fixme type hinting
        """
        the fetch headers call is asynchronous.
        once we request new headers to the interface, we expect to being triggered here.
        """
        try:
            await self._fetch_headers_lock.acquire()
            try:
                headers = list(
                    map(
                        lambda h: {
                            'block_hash': str(h[0].hash()),
                            'prev_block_hash': str(h[0].previous_block_hash),
                            'header_bytes': h[0].as_bin()
                        },
                        headers
                    )
                )
                new_headers = await self._check_headers_with_best_chain(connection, headers)
                if not new_headers:
                    return
                await self._evaluate_consensus_for_new_headers(new_headers)
                await self._save_new_headers(new_headers)
            except exceptions.HeadersInconsistencyException:
                raise ValueError  # todo fixme - per ora l'happy path...
            except exceptions.InvalidConsensusRulesException:
                Logger.p2p.exception('Connection %s has invalid blocks, asking for disconnection', connection)
                await connection.disconnect()
            self._next_fetch_headers_schedule.cancel()
            self.loop.create_task(self._fetch_headers_loop())
        finally:
            self._fetch_headers_lock.release()

    async def _fetch_headers(self):
        peers_best_height = self.interface.get_current_peers_best_height()
        if peers_best_height > self._last_processed_header['block_height']:
            self._last_connection = await self.interface.get_headers_after_hash(
                *map(
                    lambda h: h['block_hash'],
                    self._best_chain
                )
            )
