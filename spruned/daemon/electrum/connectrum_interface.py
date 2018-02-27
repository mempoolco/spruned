import asyncio

import async_timeout
import bitcoin
from async_timeout import timeout
from connectrum import ElectrumErrorResponse
from connectrum.client import StratumClient
from connectrum.svr_info import ServerInfo
import random
import binascii
import os
from spruned import settings
from spruned.abstracts import HeadersRepository
from spruned.daemon import database
from spruned.logging_factory import Logger
from spruned.tools import blockheader_to_blockhash, deserialize_header, serialize_header

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


def get_chunks_range(local_height, final_height):
    local_height = local_height + 1
    final_height = final_height + 1
    while local_height % 2016:
        local_height = local_height - 1
    res = range(local_height // 2016, final_height // 2016)
    return res


class ConnectrumInterface:
    def __init__(self, coin, app, concurrency=1, max_retries_on_discordancy=3, connections_concurrency_ratio=3):
        assert coin.value == 1
        self._peers = []
        self.concurrency = concurrency
        self.blacklisted = []
        self._keepalive = True
        self._max_retries_on_discordancy = max_retries_on_discordancy
        self._connections_concurrency_ratio = connections_concurrency_ratio
        self._current_status = None
        self._repo = None  # type: HeadersRepository
        self.app = app  # type: 'web.Application'
        self.lock = asyncio.Lock()

    def add_headers_repository(self, headers_repository: HeadersRepository):
        self._repo = headers_repository

    def _update_status(self, status):
        self._current_status = status

    def _electrum_disconnect(self):
        self._keepalive = False

    async def _evaluate_peer_best_header(self, current_best_network_header):
        print('Received best height: %s' % current_best_network_header)
        await self._handle_header(current_best_network_header)

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
            with timeout(1):
                await conn.connect(_server_info, disable_cert_verify=True)
                banner = await conn.RPC('server.banner')
                banner and self._peers.append(conn)
                self._update_status('connecting, %s' % len(self._peers))
                self.app.loop.create_task(self._subscribe_headers(conn))
                Logger.electrum.debug('ConnectrumClient - added peer %s:%s', _server[0], _server[1])
        except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
            self.blacklisted.append(_server)

    async def _subscribe_headers(self, connection: StratumClient):
        future, Q = connection.subscribe('blockchain.headers.subscribe')
        best_header = await future
        await self._handle_header(best_header)

        while 1:
            best_header = await Q.get()
            Logger.electrum.debug('New best header: %s', best_header)
            await self._handle_header(best_header[0])

    @database.atomic
    async def _handle_new_best_header(self, header):
        block_height = header.pop('block_height')
        header_hex = serialize_header(header)
        self._repo.save_header(
            blockheader_to_blockhash(header_hex),
            block_height,
            binascii.unhexlify(header_hex),
            header['prev_block_hash']
        )

    async def _handle_header(self, header: dict):
        await self.lock.acquire()
        try:
            data = self._repo.get_best_header()
            local_best_height, local_best_hash = None, None
            if data:
                local_best_height, local_best_hash = data['block_height'], data['block_hash']
            if not local_best_height or local_best_height < header['block_height'] - 1:
                await self._build_headers_chain(local_best_height, header['block_height'])
            elif local_best_height == header['block_height'] - 1:
                await self._handle_new_best_header(header)
            elif local_best_height == header['block_height']:
                serialized = serialize_header(header)
                blockhash = blockheader_to_blockhash(serialized)
                if local_best_hash == blockhash:
                    pass
                else:
                    await self._handle_headers_inconsistency(local_best_height)
        finally:
            self.lock.release()

    @database.atomic
    async def _handle_headers_inconsistency(self, local_best_height: int):
        restart_from = local_best_height - (2016*2)
        self._repo.remove_headers_since_height(restart_from)
        await self._build_headers_chain(restart_from, restart_from + 2016*3)

    def _save_header(self, x, i, header_hex):
        block_height = x * 2016 + i
        blockhash_from_header = blockheader_to_blockhash(header_hex)
        if block_height == 0:
            assert blockhash_from_header == settings.GENESIS_BLOCK
        header_data = deserialize_header(header_hex)
        self._repo.save_header(
            blockhash_from_header, block_height, binascii.unhexlify(header_hex), header_data['prev_block_hash']
        )

    @database.atomic
    async def _build_headers_chain(self, local_best_height, network_height):
        local_best_height = local_best_height or 0
        for chunk_index in get_chunks_range(local_best_height, local_best_height+4032):
            print('build headers chain, blocks between %s and %s' % (chunk_index*2016, network_height))
            data = await self.getblockheaders_chunk(chunk_index, force_peers=1)
            header = data and data[0]
            if not header:
                return
            print('Saving 2016 blocks from %s' % (chunk_index * 2016))
            for i, header_hex in enumerate([header[i:i+160] for i in range(0, len(header), 160)]):
                self._save_header(chunk_index, i, header_hex)

    async def _ping_peer(self, peer):
        try:
            with async_timeout.timeout(1):
                current_best_header = await asyncio.gather(peer.RPC('blockchain.headers.subscribe'))
                await self._evaluate_peer_best_header(current_best_header[0])
        except asyncio.TimeoutError:
            Logger.electrum.warning('Peer timeout, disconnecting')
            self._peers = [p for p in self._peers if p != peer]

    async def _keep_connections(self):
        while 1:
            if not self._keepalive:
                for peer in self._peers:
                    try:
                        peer.close()
                    except Exception:
                        Logger.electrum.exception('Error disconnecting from peer')
                break
            if len(self._peers) < self.concurrency * self._connections_concurrency_ratio:
                await self._connect_to_server()
                continue
            else:
                peer = random.choice(self._peers)
                await self._ping_peer(peer)
                self._update_status('connected, %s' % len(self._peers))
            await asyncio.sleep(30)

    async def start(self):
        Logger.electrum.debug('ConnectrumClient - connect')
        self._update_status('stopped')
        self.app.loop.create_task(self._keep_connections())
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
            if force_peers is not None and len(peers) == force_peers:
                break
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
            return []
        return responses

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
            return []
        return responses

    async def getblockheaders_chunk(self, chunks_index: int, force_peers=None):
        responses = []
        futures = [
            peer.RPC('blockchain.block.get_chunk', chunks_index)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        try:
            for response in await asyncio.gather(*futures):
                response and responses.append(response)
        except ElectrumErrorResponse:
            return []
        return responses

    async def getblockheader(self, scripthash: str, force_peers=None):
        responses = []
        futures = [
            peer.RPC('blockchain.block.get_header', scripthash)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        try:
            for response in await asyncio.gather(*futures):
                response and responses.append(response)
        except ElectrumErrorResponse:
            return []
        return responses
