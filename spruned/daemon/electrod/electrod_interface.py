import asyncio
import async_timeout
import time
from connectrum import ElectrumErrorResponse
from connectrum.client import StratumClient
from connectrum.svr_info import ServerInfo
import random
import binascii
import os
from spruned import settings
from spruned.abstracts import HeadersRepository
from spruned.daemon import database, exceptions
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


class ElectrodInterface:
    def __init__(self, coin, concurrency=1, max_retries_on_discordancy=3, connections_concurrency_ratio=3, loop=None):
        assert coin.value == 1
        self._peers = []
        self.concurrency = concurrency
        self.blacklisted = []
        self._keepalive = True
        self._max_retries_on_discordancy = max_retries_on_discordancy
        self._connections_concurrency_ratio = connections_concurrency_ratio
        self._current_status = None
        self._repo = None  # type: HeadersRepository
        self.loop = loop or asyncio.get_event_loop()
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
            with async_timeout.timeout(5):
                await conn.connect(_server_info, disable_cert_verify=True)
                banner = await conn.RPC('server.banner')
                banner and self._peers.append(conn)
                self._update_status('connecting, %s' % len(self._peers))
                self.loop.create_task(self._subscribe_headers(conn))
                Logger.electrum.debug('ConnectrumClient - added peer %s:%s', _server[0], _server[1])
        except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
            pass #self.blacklisted.append(_server)

    async def _subscribe_headers(self, connection: StratumClient):
        future, Q = connection.subscribe('blockchain.headers.subscribe')
        best_header = await future
        await self._handle_header(best_header)
        start = int(time.time())
        while connection.protocol or start + 5 > int(time.time()):
            with async_timeout.timeout(5):
                try:
                    best_header = await Q.get()
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    continue
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
        local_best_height, local_best_hash = 0, None
        try:
            await self.lock.acquire()
            data = self._repo.get_best_header()
            if data:
                local_best_height, local_best_hash = data['block_height'], data['block_hash']
            if not local_best_height or local_best_height < header['block_height'] - 1:
                await self._save_headers_chunks(local_best_height, header['block_height'])
            elif local_best_height == header['block_height'] - 1:
                await self._handle_new_best_header(header)
            elif local_best_height == header['block_height']:
                serialized = serialize_header(header)
                blockhash = blockheader_to_blockhash(serialized)
                if local_best_hash == blockhash:
                    pass
                else:
                    await self._handle_headers_inconsistency(local_best_height)
        except exceptions.HeadersInconsistencyException:
            await self._handle_headers_inconsistency(local_best_height - 64)

        finally:
            self.lock.release()

    @database.atomic
    async def _handle_headers_inconsistency(self, local_best_height: int):
        print('handle headers inconsistency, best height: %s' % local_best_height)
        if local_best_height:
            _best_height = local_best_height
            while _best_height % 2016:
                _best_height -= 1
        else:
            _best_height = 0
        self._repo.remove_headers_since_height(_best_height)

    @staticmethod
    def _parse_header(header_hex, block_height):
        blockhash_from_header = blockheader_to_blockhash(header_hex)
        if block_height == 0:
            assert blockhash_from_header == settings.GENESIS_BLOCK
        header_data = deserialize_header(header_hex)
        return {
            'block_hash': blockhash_from_header,
            'block_height': block_height,
            'header_bytes': binascii.unhexlify(header_hex),
            'prev_block_hash': header_data['prev_block_hash']
        }

    async def _fetch_headers_chunks(self, local_best_height, network_height):
        total_peers = self.concurrency * self._connections_concurrency_ratio
        requested_peers = total_peers > self.concurrency*2 and int(total_peers * 0.7) or self.concurrency
        active_peers = [peer for peer in self._pick_peers(force_peers=requested_peers) if peer.protocol]

        if len(active_peers) < requested_peers:
            print('Skipping fetch headers, connected to %s peers, needed %s' % (len(active_peers), requested_peers))
            return

        local_best_height = local_best_height or 0
        print('Fetching headers from %s peers' % len(active_peers))
        futures = []
        chunks_indexes = []
        for i, chunk_index in enumerate(get_chunks_range(local_best_height, local_best_height+len(active_peers)*2016)):
            futures.append(active_peers[i].RPC('blockchain.block.get_chunk', chunk_index))
            chunks_indexes.append(chunk_index)
        headers = []
        try:
            responses = await asyncio.gather(*futures)
        except ElectrumErrorResponse:
            return

        for chunk_index, chunk in enumerate([chunk for chunk in responses if chunk]):
            for i, header_hex in enumerate([chunk[i:i+160] for i in range(0, len(chunk), 160)]):
                height = chunks_indexes[chunk_index] * 2016 + i
                headers.append(self._parse_header(header_hex, height))
            print('Saving 2016 blocks from %s' % (chunks_indexes[chunk_index] * 2016))
        return headers

    @database.atomic
    async def _save_header(self, header_hex, block_height):
        header = self._parse_header(header_hex, block_height)
        self._repo.save_header(
            header['block_hash'],
            header['block_height'],
            header['header_bytes'],
            header['prev_block_hash']
        )

    @database.atomic
    async def _save_headers_chunks(self, local_best_height, network_height):
        headers = await self._fetch_headers_chunks(local_best_height, network_height)
        if headers:
            print('Saving %s headers, starts from %s' % (len(headers), local_best_height))
            self._repo.save_headers(headers)
            print('Saved %s headers' % len(headers))

    async def _ping_peer(self, peer):
        try:
            with async_timeout.timeout(5):
                current_best_header = await asyncio.gather(peer.RPC('blockchain.headers.subscribe'))
                await self._evaluate_peer_best_header(current_best_header[0])
        except asyncio.TimeoutError:
            Logger.electrum.warning('Peer timeout, disconnecting')
            self._peers = [p for p in self._peers if p != peer]

    async def _keep_connections(self):
        i = 0
        while 1:
            i += 1
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
                if not i % 20:
                    peer = random.choice(self._peers)
                    await self._ping_peer(peer)
                    self._update_status('connected, %s' % len(self._peers))
            await asyncio.sleep(3)
            to_remove = []
            for peer in self._peers:
                if not peer.protocol:
                    to_remove.append(peer)
                    peer.close()
            self._peers = [peer for peer in self._peers if peer not in to_remove]

    async def start(self):
        Logger.electrum.debug('ConnectrumClient - connect')
        self._update_status('stopped')
        self.loop.create_task(self._keep_connections())
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
