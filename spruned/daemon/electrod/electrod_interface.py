import asyncio
import json
import time
import random
import binascii
import os
from typing import Dict, Tuple

import async_timeout
from connectrum import ElectrumErrorResponse
from connectrum.client import StratumClient
from connectrum.svr_info import ServerInfo
from spruned.application import settings
from spruned.daemon import exceptions
from spruned.application.logging_factory import Logger
from spruned.application.tools import blockheader_to_blockhash, deserialize_header, async_delayed_task, serialize_header


class ElectrodInterface:
    MAX_ERRORS_PER_PEER_BEFORE_DISCONNECTING = 3

    def __init__(self, coin, concurrency=1, max_retries_on_discordancy=3, connections_concurrency_ratio=3):
        assert coin.value == 1
        self._coin = coin
        self._serversfile_attr = {
            1: 'bc_mainnet',
            2: 'bc_testnet'
        }
        self._peers = []
        self.concurrency = concurrency
        self.blacklisted = []
        self._keepalive = True
        self._max_retries_on_discordancy = max_retries_on_discordancy
        self._connections_concurrency_ratio = connections_concurrency_ratio
        self._current_status = None
        self._electrum_servers = self._load_electrum_servers()
        self._peers_errors = {}
        self._keep_connecting = False

    def _load_electrum_servers(self):
        _current_path = os.path.dirname(os.path.abspath(__file__))
        with open(_current_path + '/electrum_servers.json', 'r') as f:
            servers = json.load(f)
        return servers[self._serversfile_attr[self._coin.value]]

    async def get_all_connected_peers(self):
        return [peer for peer in self._peers if peer.protocol]

    def _update_status(self, status):
        self._current_status = status

    def _electrum_disconnect(self):
        self._keepalive = False

    async def _connect_to_server(self):
        _server = None
        i = 0
        while not _server:
            i += 1
            _server = random.choice(self._electrum_servers)
            _server = _server not in self.blacklisted and _server or None
            assert i < 50

        _server_info = ServerInfo(
            binascii.hexlify(os.urandom(6)).decode(),
            _server[0],
            _server[1]
        )
        conn = StratumClient()
        try:
            with async_timeout.timeout(5):
                await conn.connect(_server_info, disable_cert_verify=True)
                banner = await conn.RPC('server.banner')
                banner and self._peers.append(conn)
                self._update_status('connecting, %s' % len(self._peers))
                Logger.electrum.debug('Connected to peer %s:%s', _server[0], _server[1])
        except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
            errors = self._peers_errors[conn] = self._peers_errors.get(conn, 0) + 1
            self._handle_peer_error(conn, errors)

    async def subscribe_new_headers(self, connection: StratumClient, callback):
        future, Q = connection.subscribe('blockchain.headers.subscribe')
        start = int(time.time())
        while connection.protocol or start + 5 > int(time.time()):
            with async_timeout.timeout(5):
                try:
                    best_header = await Q.get()
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    continue
            await callback(connection, self._parse_header(best_header[0]))

    @staticmethod
    def _parse_header(electrum_header: Dict):
        header_hex = serialize_header(electrum_header)
        blockhash_from_header = blockheader_to_blockhash(header_hex)
        if electrum_header['block_height'] == 0:
            assert blockhash_from_header == settings.GENESIS_BLOCK
        header_data = deserialize_header(header_hex)
        return {
            'block_hash': blockhash_from_header,
            'block_height': electrum_header['block_height'],
            'header_bytes': binascii.unhexlify(header_hex),
            'prev_block_hash': header_data['prev_block_hash']
        }

    async def get_headers_from_chunk(self, chunk_index: int):
        chunk = await self.get_chunk(chunk_index)
        if not chunk:
            return
        hex_headers = [chunk[i:i + 160] for i in range(0, len(chunk), 160)]
        headers = []
        for i, header_hex in enumerate(hex_headers):
            header = deserialize_header(header_hex)
            header['block_height'] = int(chunk_index * 2016 + i)
            header['header_bytes'] = binascii.unhexlify(header_hex)
            header['block_hash'] = header.pop('hash')
            headers.append(header)
        return headers

    async def _keep_connections(self, on_connected=None):
        to_remove = []
        for peer in self._peers:
            if not peer.protocol:
                to_remove.append(peer)
                peer.close()
        self._peers = [peer for peer in self._peers if peer not in to_remove]
        loop = asyncio.get_event_loop()
        if not self._keepalive:
            for peer in self._peers:
                try:
                    peer.close()
                except Exception:
                    Logger.electrum.exception('Error disconnecting from peer')
            return
        if len(self._peers) >= self.concurrency and on_connected:
            on_connected and loop.create_task(on_connected())
            on_connected and Logger.electrum.debug('Electrod headers sync started.')
            loop.create_task(self._keep_connections())
            return

        peers_under_target = len(self._peers) < self.concurrency * self._connections_concurrency_ratio
        if peers_under_target:
            if not self._keep_connecting:
                self._keep_connecting = True
                Logger.electrum.debug('Peers under target, keep connecting, no sync yet.')
            await self._connect_to_server()
            loop.create_task(self._keep_connections(on_connected))
            return
        else:
            self._keep_connecting and Logger.electrum.debug('Connected to %s peers' % len(self._peers))
            self._keep_connecting = False

        loop.create_task(async_delayed_task(self._keep_connections(), 5))

    async def start(self, on_connected=None):
        self._update_status('stopped')
        await self._keep_connections(on_connected=on_connected)

    async def disconnect_from_peer(self, peer: StratumClient):
        peer.close()
        self._peers = [p for p in self._peers if p != peer]

    def _pick_peers(self, force_peers=None):
        i = 0
        peers = []
        while 1:
            i += 1
            if i > 200:
                break
            peer = self._peers and random.choice(self._peers) or None
            if not peer:
                raise exceptions.NoPeersException('No Peers Available')
            peer not in peers and peer.protocol and peers.append(peer)
            if force_peers is not None:
                if len(peers) == force_peers:
                    break
                continue
            elif len(peers) == self.concurrency:
                break
        return peers

    async def getrawtransaction(self, txid: str, force_peers=None):
        responses = []
        futures = [
            peer.RPC('blockchain.transaction.get', txid)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        try:
            for response in await asyncio.gather(*futures):
                response and responses.append(response)
        except ElectrumErrorResponse as e:
            return e.args and e.args[0]
        return responses and {"response": self._handle_responses(responses)}

    async def get_last_network_best_header(self, force_peers=1) -> (Tuple, None):
        Logger.electrum.debug('Obtaining latest network header')
        assert force_peers == 1
        peer = self._pick_peers(force_peers=force_peers)
        future, _ = peer[0].subscribe('blockchain.headers.subscribe')
        try:
            header = await future
            return peer[0], self._parse_header(header)
        except ElectrumErrorResponse:
            return

    @staticmethod
    def _handle_responses(responses):
        if len(responses) == 1:
            return responses and responses[0]
        for response in responses:
            if responses.count(response) > len(responses) / 2:
                return response
        raise exceptions.NoQuorumOnResponsesException(responses)

    def _handle_electrum_exception(self, e: ElectrumErrorResponse):
        peer: StratumClient = e.args[2]
        errors = self._peers_errors[peer] = self._peers_errors.get(peer, 0) + 1
        self._handle_peer_error(peer, errors)

    def _handle_peer_error(self, peer, errors):
        if errors > self.MAX_ERRORS_PER_PEER_BEFORE_DISCONNECTING:
            Logger.electrum.warning(
                'Multiple errors (%s) with peer %s, disconnecting' % (
                    self.MAX_ERRORS_PER_PEER_BEFORE_DISCONNECTING, peer.server_info[0]
                )
            )
            self._ban_peer(peer)

    def _ban_peer(self, peer):
        self._peers = [peer for peer in self._peers if peer != peer]
        self._peers_errors.pop(peer)
        peer.close()
        self.blacklisted.append(peer.server_info)
        del peer

    async def getaddresshistory(self, scripthash: str, force_peers=None):
        responses = []
        futures = [
            peer.RPC('blockchain.address.get_history', scripthash)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        try:
            for response in await asyncio.gather(*futures):
                response and responses.append(response)
        except ElectrumErrorResponse as e:
            return self._handle_electrum_exception(e)
        return responses and self._handle_responses(responses)

    async def get_chunk(self, chunks_index: int, force_peers=None):
        responses = []
        futures = [
            peer.RPC('blockchain.block.get_chunk', chunks_index)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        if not futures:
            raise exceptions.SprunedException('No peers')
        try:
            for response in await asyncio.gather(*futures):
                response and responses.append(response)
        except ElectrumErrorResponse as e:
            return self._handle_electrum_exception(e)
        return responses and self._handle_responses(responses)

    async def get_header(self, height: int, force_peers=None):
        responses = []
        futures = [
            peer.RPC('blockchain.block.get_header', height)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        try:
            for response in await asyncio.gather(*futures):
                response and responses.append(response)
        except ElectrumErrorResponse as e:
            return self._handle_electrum_exception(e)
        response = self._handle_responses(responses)
        return response and self._parse_header(response)

    async def get_headers_in_range_from_chunks(self, starts_from: int, ends_to: int):
        futures = []
        for chunk_index in range(starts_from, ends_to):
            futures.append(self.get_headers_from_chunk(chunk_index))
        headers = []
        try:
            for _headers in await asyncio.gather(*futures):
                _headers and headers.extend(_headers)
        except ElectrumErrorResponse as e:
            return self._handle_electrum_exception(e)
        return headers

    async def get_headers_in_range(self, starts_from: int, ends_to: int):
        chunks_range = [x for x in range(starts_from, ends_to)]
        futures = []
        for i in chunks_range:
            futures.append(self.get_header(i))
        headers = []
        try:
            for header in await asyncio.gather(*futures):
                headers.append(header)
        except ElectrumErrorResponse as e:
            return self._handle_electrum_exception(e)
        return headers

    async def estimatefee(self, blocks: int, force_peers=None):
        responses = []
        futures = [
            peer.RPC('blockchain.estimatefee', blocks)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        try:
            for response in await asyncio.gather(*futures):
                response and responses.append(response)
        except ElectrumErrorResponse as e:
            return self._handle_electrum_exception(e)
        return responses and {"response": "{:.8f}".format(min(responses))}

    async def listunspents(self, address: str, force_peers=1):
        responses = []
        futures = [
            peer.RPC('blockchain.address.listunspent', address)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        try:
            for response in await asyncio.gather(*futures):
                response and responses.append(response)
        except ElectrumErrorResponse as e:
            return self._handle_electrum_exception(e)
        return {"response": responses and self._handle_responses(responses) or []}
