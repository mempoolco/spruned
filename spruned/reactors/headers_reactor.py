import asyncio
import typing
from spruned.application.exceptions import InvalidPOWException
from spruned.application.logging_factory import Logger
from spruned.application.tools import async_delayed_task
from spruned.services import exceptions
from spruned.services.p2p.connection import P2PConnection
from spruned.services.p2p.interface import P2PInterface


class HeadersReactor:
    def __init__(
            self,
            repo,
            network_values,
            interface: P2PInterface,
            loop=asyncio.get_event_loop(),
            delayed_task=async_delayed_task,
            min_peers_agreement=1,
    ):
        self.network_values = network_values
        self.repo = repo
        self.interface = interface
        self.loop = loop or asyncio.get_event_loop()
        self.lock = asyncio.Lock()
        self.subscriptions = []
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
        self._best_chain = []
        self._best_chain_height_index = {}

    def _get_height_for_hash(self, block_hash: str) -> typing.Optional[int]:
        return self._best_chain_height_index.get(block_hash)

    def add_on_new_header_callback(self, callback: callable):
        self._on_new_best_header_callbacks.append(callback)

    def _set_best_chain(self, best_chain: typing.List[typing.Dict]):
        assert not self._best_chain
        assert best_chain
        for i, header in enumerate(best_chain):
            self._best_chain.append(header)
            self._best_chain_height_index[header['block_hash']] = header['block_height']

    def _append_to_best_chain(self, header: typing.Dict):
        self._best_chain.append(header)
        self._best_chain_height_index[header['block_hash']] = header['block_height']
        b = self._best_chain.pop(0)
        self._best_chain_height_index.pop(b['block_hash'])

    async def start(self):
        request_back_to_headers = 100
        best_height = await self.repo.get_best_height()
        header = await self.repo.get_header_at_height(max(best_height - request_back_to_headers, 0))
        best_chain = await self.repo.get_headers(header['block_hash'])
        self._set_best_chain(best_chain)
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
        start_from_height = self._get_height_for_hash(headers[0]['prev_block_hash'])
        if start_from_height is not None \
                and start_from_height + len(headers) + 1 > self._best_chain[-1]['block_height']:
            headers[0]['block_height'] = start_from_height + 1
            has_new_headers = await self._evaluate_received_headers(headers)
        else:
            # Received an header that it is not in sync with what we know, nor we have requested it.
            # Could be anything. Discard it at the moment: there's the fallback task.
            has_new_headers = False
        return has_new_headers

    async def _evaluate_received_headers(self, headers: typing.List) -> typing.Optional[typing.List]:
        start_height = self._best_chain[0]['block_height']
        pos = headers[0]['block_height'] - start_height
        assert pos >= 0
        match_headers = self._best_chain[pos-1:]
        if any(
            filter(
                lambda h: str(h[0]['prev_block_hash']) != h[1]['block_hash'],
                zip(headers, match_headers)
            )
        ):
            raise exceptions.HeadersInconsistencyException(headers)
        p = len(match_headers) - 1
        new_headers = headers[p:]
        if not new_headers:
            return
        new_headers[0]['block_height'] = headers[0]['block_height'] + p
        return new_headers

    async def _evaluate_consensus_for_new_headers(self, headers: typing.List):
        """
        ensure:
        - chain-link is ok
        - pow is ok
        - difficulty is ok
        """
        for i, h in enumerate(headers):
            if i:
                headers[i]['block_height'] = headers[i-1]['block_height'] + 1
                prev_hash = headers[i-1]['block_hash']
                if prev_hash != h['prev_block_hash']:
                    raise exceptions.ChainBrokenException(
                        '%s != %s', prev_hash, h['prev_block_hash']
                    )
            try:
                self.network_values['header_verify'](
                    h['header_bytes'],
                    bytes.fromhex(h['block_hash'])
                )
            except InvalidPOWException:
                raise exceptions.InvalidHeaderProofException
            # todo difficulty \ chainwork \ activations flags
        return headers

    async def _save_new_headers(self, headers: typing.List):
        await self.repo.save_headers(headers)
        for header in headers:
            self._append_to_best_chain(header)

    async def on_headers(self, connection: P2PConnection, headers: typing.List):  # fixme type hinting
        """
        the fetch headers call is asynchronous.
        once we request new headers to the interface, we expect to being triggered here.
        """
        await self._fetch_headers_lock.acquire()
        try:
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
                if new_headers:
                    Logger.p2p.debug('Received %s new headers' % len(new_headers))
                    new_headers = await self._evaluate_consensus_for_new_headers(new_headers)
                    await self._save_new_headers(new_headers)
                    self._next_fetch_headers_schedule.cancel()
                    self.loop.create_task(self._fetch_headers_loop())
                connection.add_success(score=2)  # reward the connection
            except exceptions.HeadersInconsistencyException:
                raise ValueError  # fixme - wait wait, let's do the happy path...
            except exceptions.InvalidConsensusRulesException:
                Logger.p2p.exception('Connection %s has invalid blocks, asking for disconnection', connection)
                await connection.disconnect()
        finally:
            self._fetch_headers_lock.release()

    async def _fetch_headers(self):
        """
        fetch headers random check to neighbors for the blockchain they know from a bit back in time.
        """
        if not self._best_chain:
            return
        elif len(self._best_chain) == 1:
            chain = self._best_chain
        else:
            chain = self._best_chain[-6:-3]
        self._last_connection = await self.interface.get_headers_after_hash(
            *map(
                lambda h: h['block_hash'],
                chain
            )
        )