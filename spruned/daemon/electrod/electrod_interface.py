import asyncio
import time
import random
import binascii
import os
import async_timeout
from connectrum import ElectrumErrorResponse
from connectrum.client import StratumClient
from connectrum.svr_info import ServerInfo
from spruned import settings
from spruned.daemon import exceptions
from spruned.logging_factory import Logger
from spruned.tools import blockheader_to_blockhash, deserialize_header, async_delayed_task, serialize_header

ELECTRUM_SERVERS = [
    ["134.119.179.55", "s"],
    ["165.227.22.180", "s"],
    ["176.9.155.246", "s"],
    ["185.64.116.15", "s"],
    ["46.166.165.18", "s"],
    ["E-X.not.fyi", "s"],
    ["Electrum.GlowHost.com", "s"],
    ["VPS.hsmiths.com", "s"],
    ["alviss.coinjoined.com", "s"],
    ["aspinall.io", "s"],
    ["bitcoin.cluelessperson.com", "s"],
    ["bitcoin.maeyanie.com", "s"],
    ["bitcoins.sk", "s"],
    ["btc.cihar.com", "s"],
    ["btc.pr0xima.de", "s"],
    ["cryptohead.de", "s"],
    ["daedalus.bauerj.eu", "s"],
    ["e-1.claudioboxx.com", "s"],
    ["e-2.claudioboxx.com", "s"],
    ["e-3.claudioboxx.com", "s"],
    ["e.keff.org", "s"],
    ["ele.lightningnetwork.xyz", "s"],
    ["ele.nummi.it", "s"],
    ["elec.luggs.co", "s"],
    ["electrum-server.ninja", "s"],
    ["electrum.achow101.com", "s"],
    ["electrum.akinbo.org", "s"],
    ["electrum.anduck.net", "s"],
    ["electrum.antumbra.se", "s"],
    ["electrum.backplanedns.org", "s"],
    ["electrum.be", "s"],
    ["electrum.coinucopia.io", "s"],
    ["electrum.cutie.ga", "s"],
    ["electrum.festivaldelhumor.org", "s"],
    ["electrum.hsmiths.com", "s"],
    ["electrum.infinitum-nihil.com", "s"],
    ["electrum.leblancnet.us", "s"],
    ["electrum.mindspot.org", "s"],
    ["electrum.nute.net", "s"],
    ["electrum.petrkr.net", "s"],
    ["electrum.poorcoding.com", "s"],
    ["electrum.qtornado.com", "s"],
    ["electrum.taborsky.cz", "s"],
    ["electrum.villocq.com", "s"],
    ["electrum.vom-stausee.de", "s"],
    ["electrum0.snel.it", "s"],
    ["electrum2.everynothing.net", "s"],
    ["electrum2.villocq.com", "s"],
    ["electrum3.hachre.de", "s"],
    ["electrumx-core.1209k.com", "s"],
    ["electrumx.adminsehow.com", "s"],
    ["electrumx.bot.nu", "s"],
    ["electrumx.donsomhong.net", "s"],
    ["electrumx.gigelf.eu", "s"],
    ["electrumx.kekku.li", "s"],
    ["electrumx.nmdps.net", "s"],
    ["electrumx.schneemensch.net", "s"],
    ["electrumx.soon.it", "s"],
    ["electrumx.westeurope.cloudapp.azure.com", "s"],
    ["elx01.knas.systems", "s"],
    ["elx2018.mooo.com", "s"],
    ["enode.duckdns.org", "s"],
    ["erbium1.sytes.net", "s"],
    ["helicarrier.bauerj.eu", "s"],
    ["icarus.tetradrachm.net", "s"],
    ["ip101.ip-54-37-91.eu", "s"],
    ["ip119.ip-54-37-91.eu", "s"],
    ["ip120.ip-54-37-91.eu", "s"],
    ["ip239.ip-54-36-234.eu", "s"],
    ["kirsche.emzy.de", "s"],
    ["mdw.ddns.net", "s"],
    ["mooo.not.fyi", "s"],
    ["ndnd.selfhost.eu", "s"],
    ["node.ispol.sk", "s"],
    ["node.xbt.eu", "s"],
    ["noserver4u.de", "s"],
    ["orannis.com", "s"],
    ["qmebr.spdns.org", "s"],
    ["rbx.curalle.ovh", "s"],
    ["shogoth.no-ip.info", "s"],
    ["songbird.bauerj.eu", "s"],
    ["spv.48.org", "s"],
    ["such.ninja", "s"],
    ["sumBTC.mooo.com", "s"],
    ["tardis.bauerj.eu", "s"],
    ["technetium.network", "s"],
    ["us01.hamster.science", "s"],
    ["v25437.1blu.de", "s"],
    ["vps-m-01.donsomhong.net", "s"],
    ["walle.dedyn.io", "s"],
    ["ecdsa.net", "s"],
    ["erbium1.sytes.net", "s"],
    ["gh05.geekhosters.com", "s"]
]


class ElectrodInterface:
    def __init__(self, coin, concurrency=1, max_retries_on_discordancy=3, connections_concurrency_ratio=3):
        assert coin.value == 1
        self._peers = []
        self.concurrency = concurrency
        self.blacklisted = []
        self._keepalive = True
        self._max_retries_on_discordancy = max_retries_on_discordancy
        self._connections_concurrency_ratio = connections_concurrency_ratio
        self._current_status = None

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
            _server = random.choice(ELECTRUM_SERVERS)
            _server = _server not in self.blacklisted and _server or None
            assert i < 50

        _server_info = ServerInfo(
            binascii.hexlify(os.urandom(6)).decode(),
            _server[0],
            _server[1]
        )
        try:
            conn = StratumClient()
            with async_timeout.timeout(5):
                await conn.connect(_server_info, disable_cert_verify=True)
                banner = await conn.RPC('server.banner')
                banner and self._peers.append(conn)
                self._update_status('connecting, %s' % len(self._peers))
                Logger.electrum.debug('ConnectrumClient - added peer %s:%s', _server[0], _server[1])
        except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
            pass #self.blacklisted.append(_server)

    async def subscribe_new_headers(self, connection: StratumClient, callback):
        _, Q = connection.subscribe('blockchain.headers.subscribe')
        start = int(time.time())
        while connection.protocol or start + 5 > int(time.time()):
            with async_timeout.timeout(5):
                try:
                    best_header = await Q.get()
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    continue
            callback(self._parse_header(best_header[0]))

    @staticmethod
    def _parse_header(electrum_header):
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

    async def get_headers_in_range(self, starts_from, ends_to):
        chunks_range = [x for x in range(starts_from, ends_to)]
        print(chunks_range)
        futures = [self.get_headers_from_chunk(i) for i in chunks_range]
        headers = []
        _ = [headers.extend(response) for response in await asyncio.gather(*[f for f in futures])]
        return headers

    async def get_headers_from_chunk(self, chunk_index: int):
        chunk = await self.get_chunk(chunk_index, force_peers=1)
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
        peers_under_target = len(self._peers) < self.concurrency * self._connections_concurrency_ratio
        if peers_under_target:
            await self._connect_to_server()
            loop.create_task(self._keep_connections(on_connected))
            return

        on_connected and loop.create_task(on_connected())
        loop.create_task(async_delayed_task(self._keep_connections(), 30))

    async def start(self, on_connected=None):
        Logger.electrum.debug('ConnectrumClient - connect')
        self._update_status('stopped')
        await self._keep_connections(on_connected=on_connected)
        Logger.electrum.debug('ConnectrumClient - connections spawned')

    def _pick_peers(self, force_peers=None):
        i = 0
        peers = []
        while 1:
            i += 1
            if i > 100:
                break
            peer = random.choice(self._peers)
            peer not in peers and peers.append(peer)
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
        except ElectrumErrorResponse:
            return
        return responses and self._handle_responses(responses)

    async def get_last_network_best_header(self, force_peers=1):
        responses = []
        futures = [
            peer.RPC('blockchain.headers.subscribe')
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        try:
            for response in await asyncio.gather(*futures):
                response and responses.append(response)
        except ElectrumErrorResponse:
            return
        response = self._handle_responses(responses)
        return response and self._parse_header(response)

    @staticmethod
    def _handle_responses(responses):
        if len(responses) == 1:
            return responses and responses[0]
        for response in responses:
            if responses.count(response) > len(responses) / 2:
                return response
        raise exceptions.NoQuorumOnResponsesException

    async def getaddresshistory(self, scripthash: str, force_peers=None):
        responses = []
        futures = [
            peer.RPC('blockchain.address.get_history', scripthash)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        try:
            for response in await asyncio.gather(*futures):
                response and responses.append(response)
        except ElectrumErrorResponse:
            return
        return self._handle_responses(responses)

    async def get_chunk(self, chunks_index: int, force_peers=None):
        responses = []
        futures = [
            peer.RPC('blockchain.block.get_chunk', chunks_index)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        try:
            for response in await asyncio.gather(*futures):
                response and responses.append(response)
        except ElectrumErrorResponse:
            return
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
        except ElectrumErrorResponse:
            return
        response = self._handle_responses(responses)
        return response and self._parse_header(response)

    async def get_headers_in_range_from_chunks(self, starts_from: int, ends_to: int):
        print('Fetching headers between %s and %s' % (starts_from, ends_to))
        futures = []
        for chunk_index in range(starts_from, ends_to):
            futures.append(self.get_headers_from_chunk(chunk_index))
        headers = []
        for header in await asyncio.gather(*futures):
            header and headers.append(header)
        return headers