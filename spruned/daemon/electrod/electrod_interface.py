import asyncio
import json
import random
import binascii
import os
from typing import Dict

import async_timeout
import time
from connectrum import ElectrumErrorResponse
from connectrum.client import StratumClient
from connectrum.svr_info import ServerInfo
from spruned.application import settings
from spruned.daemon import exceptions
from spruned.application.logging_factory import Logger
from spruned.application.tools import blockheader_to_blockhash, deserialize_header, async_delayed_task, serialize_header


class ElectrodInterface:
    MAX_ERRORS_PER_PEER_BEFORE_DISCONNECTING = 5

    def __init__(
            self,
            coin,
            concurrency=1,
            connections_concurrency_ratio=3,
            loop=asyncio.get_event_loop(),
            stratum_client=StratumClient
    ):
        assert coin.value == 1
        self._coin = coin
        self._serversfile_attr = {
            1: 'bc_mainnet',
            2: 'bc_testnet'
        }
        self._checkpoints = settings.CHECKPOINTS
        self._peers = []
        self.concurrency = concurrency
        self.blacklisted = {}
        self._keepalive = True
        self._connections_concurrency_ratio = connections_concurrency_ratio
        self._current_status = None
        self._electrum_servers = self._load_electrum_servers()
        self._peers_errors = {}
        self._keep_connecting = False
        self.on_new_header_callback = lambda a, b: True
        self.loop = loop
        self._peer_ban_time = 120
        self._stratum_client = stratum_client

    def add_header_subscribe_callback(self, value):
        self.on_new_header_callback = value

    def _load_electrum_servers(self):
        _current_path = os.path.dirname(os.path.abspath(__file__))
        with open(_current_path + '/electrum_servers.json', 'r') as f:
            servers = json.load(f)
        return servers[self._serversfile_attr[self._coin.value]]

    def get_all_connected_peers(self):
        return [peer for peer in self._peers if peer.protocol]

    def _update_status(self, status):
        self._current_status = status

    def _electrum_disconnect(self):
        self._keepalive = False

    async def _rpc_call(self, peer: StratumClient, *args, _r=0):
        try:
            return await peer.RPC(*args)
        except asyncio.InvalidStateError:
            Logger.electrum.debug('InvalidStateError', exc_info=True)
            if not _r:
                return await self._rpc_call(peer, *args, _r+1)  # retry
            return self.handle_peer_error(peer)
        except (TimeoutError, asyncio.TimeoutError) as e:
            Logger.electrum.error('Timeout error: %s', e)
            self._peers_errors[peer] = 99
            self.handle_peer_error(peer)

    async def _connect_to_server(self):
        server = None
        i = 0
        while not server:
            i += 1
            server = random.choice(self._electrum_servers)
            if not server or self._is_banned(hostname=server[0], ports=server[1]):
                continue
            if i > 50:
                raise exceptions.SprunedException('Cannot find electrum servers to connect')
        _server_info = ServerInfo(binascii.hexlify(os.urandom(6)).decode(), server[0], server[1])
        peer = self._stratum_client()
        try:
            with async_timeout.timeout(10):
                await peer.connect(_server_info, disable_cert_verify=True)
                version = await self._rpc_call(peer, 'server.version')
                version and self._peers.append(peer)
                self._update_status('connecting, %s' % len(self._peers))
                Logger.electrum.debug('Connected to electrum server %s:%s', server[0], server[1])
                return peer
        except (ConnectionRefusedError, asyncio.TimeoutError, OSError, asyncio.CancelledError):
            self.handle_peer_error(peer)

    def _parse_header(self, electrum_header: Dict):
        header_hex = serialize_header(electrum_header)
        blockhash_from_header = blockheader_to_blockhash(header_hex)
        if electrum_header['block_height'] in self._checkpoints:
            if self._checkpoints[electrum_header['block_height']] != blockhash_from_header:
                raise exceptions.NetworkHeadersInconsistencyException
        header_data = deserialize_header(header_hex)
        return {
            'block_hash': blockhash_from_header,
            'block_height': electrum_header['block_height'],
            'header_bytes': binascii.unhexlify(header_hex),
            'prev_block_hash': header_data['prev_block_hash'],
            'timestamp': header_data['timestamp']
        }

    async def get_headers_from_chunk(self, chunk_index: int, force_peers=None):
        chunk = await self.get_chunk(chunk_index, force_peers=force_peers)
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

    async def _disconnect(self):
        for peer in self._peers:
            try:
                peer.close()
            except Exception:
                Logger.electrum.exception('Error disconnecting from peer')
        return

    async def _keep_connections(self, on_connected=None, r=1):
        if not self._keepalive:
            await self._disconnect()
            return
        for peer in self._peers:
            if not peer.protocol:
                self.handle_peer_error(peer)
        peers_under_target = len(self._peers) < self.concurrency * self._connections_concurrency_ratio
        if peers_under_target:
            if not self._keep_connecting:
                self._keep_connecting = True
                Logger.electrum.debug('Peers under target, keep connecting, no sync yet.')
            peer = await self._connect_to_server()
            peer and self.on_new_header_callback and self.loop.create_task(self.subscribe_headers(peer))
            self.loop.create_task(self._keep_connections(on_connected, r=r+1))
            return
        else:
            self._keep_connecting and Logger.electrum.debug('Connected to %s peers' % len(self._peers))
            self._keep_connecting = False
            on_connected and self.loop.create_task(on_connected())
            self.loop.create_task(async_delayed_task(self._keep_connections(r=r+1), 5, disable_log=False))

    async def _ping_peer(self, peer):
        try:
            res = await self._rpc_call(peer, 'server.version')
            Logger.electrum.debug('Ping peer %s: Pong %s', peer.server_info, res)
            assert peer.protocol
        except:
            self.handle_peer_error(peer)

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
                raise exceptions.NoPeersException('Too many iterations, No Peers Available')
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
            self._rpc_call(peer, 'blockchain.transaction.get', txid)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        try:
            async with async_timeout.timeout(5):
                for response in await asyncio.gather(*futures):
                    response and responses.append(response)
        except (ElectrumErrorResponse, asyncio.TimeoutError)as e:
            return self._handle_electrum_exception(e)
        return responses and {"response": self._handle_responses(responses)}

    async def subscribe_headers(self, peer: StratumClient):
        try:
            first = True
            future, q = peer.subscribe('blockchain.headers.subscribe')
            header = await future
            while peer.protocol:
                if first:
                    parsed_header = self._parse_header(header)
                    Logger.electrum.debug('subscribing headers from peer (%s). starting from %s (%s)',
                                          peer.server_info, parsed_header['block_hash'], parsed_header['block_height'])
                    self.loop.create_task(self.on_new_header_callback(peer, parsed_header))
                    Logger.electrum.debug('waiting for new headers from peer %s', peer.server_info)
                header = await q.get()
                first = False
                Logger.electrum.debug('new header from peer (%s): %s', peer.server_info, header[0])
                self.loop.create_task(self.on_new_header_callback(peer, self._parse_header(header[0])))
            Logger.electrum.error('Lost subscription on peer %s', peer and peer.server_info)
            self.handle_peer_error(peer)
        except (TimeoutError, ConnectionError, asyncio.TimeoutError, asyncio.CancelledError):
            Logger.electrum.exception('Subscribe exception for peer %s' % peer.server_info)
            peer_errors = self.handle_peer_error(peer)
            if peer_errors is None:
                Logger.electrum.error('subscribe_headers errors exceeded, disconnecting.')
                return
            Logger.electrum.warning(
                'subscribe_headers, peer %s, error n.%s, retrying in 5s', peer.server_info, peer_errors
            )
            self.loop.create_task(async_delayed_task(self.subscribe_headers(peer), 5))

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
        self.handle_peer_error(peer)

    def handle_peer_error(self, peer):
        try:
            errors = self._peers_errors[peer] = self._peers_errors.get(peer, 0) + 1
            if not peer.protocol or errors > self.MAX_ERRORS_PER_PEER_BEFORE_DISCONNECTING:
                Logger.electrum.warning(
                    'Multiple errors (%s) with peer %s, disconnecting',
                    self.MAX_ERRORS_PER_PEER_BEFORE_DISCONNECTING,
                    peer.server_info
                )
                self._ban_peer(peer)
                return
            return errors
        except:
            Logger.electrum.exception('Unhandled exception on handle_peer_error')

    def _ban_peer(self, peer: StratumClient):
        self._peers = [peer for peer in self._peers if peer != peer]
        self._peers_errors.pop(peer)
        try:
            peer.close()
        except:
            Logger.electrum.error('Error closing with peer while banning it')
        entry = '%s:%s' % (peer.server_info['hostname'], peer.server_info['ports'])
        self.blacklisted[entry] = int(time.time())

    def _is_banned(self, hostname, ports) -> bool:
        now = int(time.time())
        bl = {}
        for p, t in self.blacklisted.items():
            if now - t < self._peer_ban_time:
                bl[p] = t
        self.blacklisted = bl
        return '%s:%s' % (hostname, ports) in self.blacklisted

    async def getaddresshistory(self, scripthash: str, force_peers=None):
        responses = []
        futures = [
            self._rpc_call(peer, 'blockchain.address.get_history', scripthash)
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
            self._rpc_call(peer, 'blockchain.block.get_chunk', chunks_index)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        if not futures:
            raise exceptions.NoPeersException('No peers')
        try:
            for response in await asyncio.gather(*futures):
                response and responses.append(response)
        except ElectrumErrorResponse as e:
            return self._handle_electrum_exception(e)
        return responses and self._handle_responses(responses)

    async def get_header(self, height: int, force_peers=1, fail_silent_out_of_range=False, get_peer=False):
        responses = []
        peers = self._pick_peers(force_peers=force_peers)
        futures = [
            self._rpc_call(peer, 'blockchain.block.get_header', height)
            for peer in peers
        ]
        if get_peer and force_peers != 1:
            raise exceptions.SprunedException('Incompatible params')
        try:
            for response in await asyncio.gather(*futures):
                response and responses.append(response)
        except ElectrumErrorResponse as e:
            if fail_silent_out_of_range:
                if 'out of range' in str(e):
                    return
            return self._handle_electrum_exception(e)
        response = self._handle_responses(responses)
        if get_peer:
            return peers[0], (response and self._parse_header(response))
        return response and self._parse_header(response)

    async def get_headers_in_range_from_chunks(self, starts_from: int, ends_to: int):
        futures = []
        for chunk_index in range(starts_from, ends_to):
            futures.append(self.get_headers_from_chunk(chunk_index, force_peers=1))
        headers = []
        try:
            for _headers in await asyncio.gather(*futures):
                _headers and headers.extend(_headers)
        except ElectrumErrorResponse as e:
            return self._handle_electrum_exception(e)
        return headers

    async def get_headers_in_range(self, starts_from: int, ends_to: int, force_peers=None):
        chunks_range = [x for x in range(starts_from, ends_to)]
        futures = []
        for i in chunks_range:
            futures.append(self.get_header(i, force_peers=force_peers))
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
            self._rpc_call(peer, 'blockchain.estimatefee', blocks)
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
            self._rpc_call(peer, 'blockchain.address.listunspent', address)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        try:
            for response in await asyncio.gather(*futures):
                response and responses.append(response)
        except ElectrumErrorResponse as e:
            return self._handle_electrum_exception(e)
        return {"response": responses and self._handle_responses(responses) or []}
