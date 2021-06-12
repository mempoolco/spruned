import asyncio
import time
import typing

from spruned.application import consensus
from spruned.application.exceptions import InvalidPOWException, ConsensusNotReachedException
from spruned.application.logging_factory import Logger
from spruned.services import exceptions
from spruned.services.p2p.connection import P2PConnection
from spruned.services.p2p.interface import P2PInterface
from spruned.utils import async_retry


class HeadersReactor:
    def __init__(
            self,
            repo,
            network_values,
            interface: P2PInterface,
            loop=asyncio.get_event_loop(),
            min_peers_agreement=1,
    ):
        self.network_values = network_values
        self.repo = repo
        self.interface = interface
        self.loop = loop or asyncio.get_event_loop()
        self.lock = asyncio.Lock()
        self._sync_errors = 0
        self.new_headers_fallback_poll_interval = 10
        self.initial_headers_download = True
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
        self.interface.set_local_current_header(header)
        self._best_chain_height_index[header['block_hash']] = header['block_height']
        self._best_chain_height_index.pop(self._best_chain.pop(0)['block_hash'])

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

            if self.initial_headers_download and \
                    self._best_chain[-1]['block_height'] >= self.interface.get_current_peers_best_height():
                self.initial_headers_download = False
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
        pos_after_match = len(match_headers) - 1
        new_headers = headers[pos_after_match:]
        if not new_headers:
            return
        new_headers[0]['block_height'] = headers[0]['block_height'] + pos_after_match
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

    @staticmethod
    def _format_headers(headers: typing.List):
        return map(
            lambda h: {
                'block_hash': str(h[0].hash()),
                'prev_block_hash': str(h[0].previous_block_hash),
                'header_bytes': h[0].as_bin()
            },
            headers
        )

    async def on_headers(self, connection: P2PConnection, headers: typing.List):  # fixme type hinting
        """
        the fetch headers call is asynchronous.
        once we request new headers to the interface, we expect to being triggered here.
        """
        await self._fetch_headers_lock.acquire()
        try:
            headers = list(self._format_headers(headers))
            new_headers = await self._check_headers_with_best_chain(connection, headers)
            if not new_headers:
                connection.add_success(score=1)  # ack
                return
            await self.ensure_agreement_for_headers(
                connection,
                self._get_headers_for_agreement(new_headers)
            )
            await self._handle_new_headers(new_headers)
            connection.add_success(score=2)  # ack & reward
        except exceptions.HeadersInconsistencyException:
            raise ValueError  # fixme - wait wait, let's do the happy path...
        except exceptions.InvalidConsensusRulesException:
            Logger.p2p.exception('Connection %s has invalid blocks, asking for disconnection', connection)
            await connection.disconnect()
        finally:
            self._fetch_headers_lock.release()

    async def _handle_new_headers(self, new_headers: typing.List[typing.Dict]):
        Logger.p2p.debug('Received %s new headers' % len(new_headers))
        new_headers = await self._evaluate_consensus_for_new_headers(new_headers)
        await self._save_new_headers(new_headers)
        self._next_fetch_headers_schedule.cancel()
        self.loop.create_task(self._fetch_headers_loop())

    def _get_headers_for_agreement(self, headers):
        """
        Return a chunk of headers from the known best_chain, to be checked for agreement between multiple peers.
        """
        assert headers[0]['prev_block_hash'] == self._best_chain[-1]['block_hash']
        for i, h in enumerate(headers, start=1):
            h['block_height'] = self._best_chain[-1]['block_height'] + i
        return (self._best_chain[-2:] + headers)[-3:]

    async def _fetch_headers(self):
        """
        fetch headers from a certain point.
        """
        if not self._best_chain:
            # we know nothing on the current chain
            return
        elif len(self._best_chain) == 1:
            chain = self._best_chain
        else:
            chain = self._best_chain[-6:-3]
        # ask for an header, set the peer responding as the last connection we talked with.

        self._last_connection = await self.interface.get_headers_after_hash(
            *map(
                lambda h: h['block_hash'],
                chain
            )
        )

    @staticmethod
    async def _fetch_header_blocking(connection, responses: typing.Dict, headers: typing.List[typing.Dict]):
        try:
            h = await connection.fetch_headers_blocking(
                *map(lambda x: x['block_hash'], headers[:-1]),
                stop_at_hash=headers[-1]['block_hash']
            )
            responses[connection] = h
            connection.add_success()
        except asyncio.exceptions.TimeoutError:
            Logger.p2p.debug('fetch_header_blocking timeout error')

    @staticmethod
    def _evaluate_agreement_for_headers(
            _headers: typing.List[typing.Dict], _responses: typing.Dict, origin_peer: P2PConnection
    ):
        """
        This method is called when the headers reactor intend to save new headers on the database.

        It evaluates agreement on headers between peers who responded the getheaders call.
        It is part of the `ensure_agreement_for_headers` flow.
        Once the agreement is done, all the P2PConnection object that agrees, are updated.

        """
        connections_by_hashes: typing.Dict[str:P2PConnection] = {}
        heights_by_hashes: typing.Dict[str:int] = {}

        for x in range(0, len(_headers[2:])):
            d = []
            for c, r in _responses.items():
                blockhash = str(r['headers'][x][0].hash())
                block_height = _headers[2+x]['block_height']
                heights_by_hashes[blockhash] = block_height
                connections_by_hashes.setdefault(blockhash, [])
                connections_by_hashes[blockhash].append(c)
                d.append(blockhash)

            d.append(_headers[1+x]['block_hash'])
            agreement_on_hash = consensus.reach_consensus_on_value(*d)

            agreement_on_height = heights_by_hashes[agreement_on_hash]
            if origin_peer.last_block_index < agreement_on_height:
                origin_peer.last_block_index = agreement_on_height

            for c in connections_by_hashes[agreement_on_hash]:
                if c.last_block_index < agreement_on_height:
                    Logger.p2p.info(
                        'Updating current height for peer %s. %s - %s',
                        c.hostname, agreement_on_height, agreement_on_hash
                    )
                    c.last_block_index = agreement_on_height

    @async_retry(retries=2, wait=2, on_exception=exceptions.PeersDoesNotAgreeOnHeadersException)
    async def ensure_agreement_for_headers(
        self,
        peer: P2PConnection,
        headers: typing.List[typing.Dict]
    ):
        """
        This method makes sure that other peers agree with the headers we have.
        Only some headers are checked.
        """
        if headers[0]['block_height'] + len(headers) < max(self.network_values['checkpoints']):
            return True
        total_peers_needed_to_agree = self.interface.pool.required_connections - 1
        if not total_peers_needed_to_agree:
            return True  # spruned is set to connect to a single peer.
        requested: typing.Set = {peer.uid, }
        start = time.time()
        responses = dict()
        while time.time() - start <= 10:
            for connection in self.interface.pool.established_connections:
                if connection.uid in requested:
                    continue
                self.loop.create_task(
                    self._fetch_header_blocking(connection, responses, headers[-3:])
                )
                requested.add(connection.uid)
            await asyncio.sleep(0.3)
            if 1 + len(responses) > self.interface.pool.required_connections * 0.6:
                try:
                    return self._evaluate_agreement_for_headers(headers, responses, peer)
                except ConsensusNotReachedException:
                    continue
        raise exceptions.PeersDoesNotAgreeOnHeadersException
