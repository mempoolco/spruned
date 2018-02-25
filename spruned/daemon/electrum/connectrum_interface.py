import asyncio

import async_timeout
from async_timeout import timeout
from connectrum.client import StratumClient
from connectrum.svr_info import ServerInfo
import random
import binascii
import os
from spruned.logging_factory import Logger


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
    ["walle.dedyn.io", "s"]
]


class ConnectrumInterface:
    def __init__(
            self,
            coin,
            app,
            loop=None,
            concurrency=1,
            max_retries_on_discordancy=3,
            connections_concurrency_ratio=3,
    ):
        self.loop = loop or asyncio.get_event_loop()
        assert coin.value == 1
        self._peers = []
        self.concurrency = concurrency
        self.blacklisted = []
        self._keepalive = True
        self._max_retries_on_discordancy = max_retries_on_discordancy
        self._connections_concurrency_ratio = connections_concurrency_ratio
        self._current_status = None
        self._headers_observers = []
        self.app = app  # type: 'web.Application'

    def add_headers_observer(self, headers_observer):
        self._headers_observers.append(headers_observer)

    def _update_status(self, status):
        self._current_status = status

    def _electrum_disconnect(self):
        self._keepalive = False

    def _evaluate_peer_best_height(self, current_best_height):
        print('Received best height: %s' % current_best_height)

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
        for observer in self._headers_observers:
            observer.on_best_header(best_header)

        while 1:
            best_header = await Q.get()
            Logger.electrum.debug('New best header: %s', best_header)
            for observer in self._headers_observers:
                observer.on_best_header(best_header)

    async def _ping_peer(self, peer):
        try:
            with async_timeout.timeout(1) as t:
                current_best_height = await asyncio.gather(peer.RPC('blockchain.headers.subscribe'))
                self._evaluate_peer_best_height(current_best_height)
        except asyncio.TimeoutError:
            self._peers = [p for p in self._peers if p != peer]

    async def _keep_connections(self):
        while 1:
            if not self._keepalive:
                for peer in self._peers:
                    peer.close()
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
        for response in await asyncio.gather(*futures):
            response and responses.append(response)
        return responses

    async def getaddresshistory(self, scripthash: str, force_peers=None):
        responses = []
        futures = [
            peer.RPC('blockchain.address.get_history', scripthash)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        for response in await asyncio.gather(*futures):
            response and responses.append(response)
        return responses

    async def getblockheaders_chunk(self, chunks_index: int, force_peers=None):
        responses = []
        futures = [
            peer.RPC('blockchain.address.get_chunk', chunks_index)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        for response in await asyncio.gather(*futures):
            response and responses.append(response)
        return responses

    async def getblockheader(self, scripthash: str, force_peers=None):
        responses = []
        futures = [
            peer.RPC('blockchain.block.get_header', scripthash)
            for peer in self._pick_peers(force_peers=force_peers)
        ]
        for response in await asyncio.gather(*futures):
            response and responses.append(response)
        return responses
