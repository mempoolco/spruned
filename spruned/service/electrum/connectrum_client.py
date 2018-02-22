import asyncio
import queue
import time
from async_timeout import timeout
from connectrum import ElectrumErrorResponse
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


class ConnectrumClient():
    def __init__(
            self,
            coin,
            loop=None,
            concurrency=1,
            max_retries_on_discordancy=3,
            connections_concurrency_ratio=3):
        self.loop = loop or asyncio.get_event_loop()
        assert coin.value == 1
        self._peers = []
        self.concurrency = concurrency
        self.blacklisted = []
        self._keepalive = True
        self._cmd_queue = None  # type: queue.Queue
        self._res_queue = None  # type: queue.Queue
        self._status_queue = None  # type: queue.Queue
        self._max_retries_on_discordancy = max_retries_on_discordancy
        self._connections_concurrency_ratio = connections_concurrency_ratio
        self._current_status = None

    async def _resolve_cmd(self, command_artifact, retry=0):
        Logger.electrum.debug('ConnectrumClient - resolve_cmd, command: %s (retry: %s)', command_artifact, retry)
        if retry >= self._max_retries_on_discordancy:
            raise RecursionError
        cmds = {
            'die': self._electrum_disconnect,
            'getrawtransaction': self._electrum_getrawtransaction,
            'getaddresshistory': self._electrum_getaddresshistory,
            'getblockheader': self._electrum_getblockheader
        }
        responses = []
        await cmds[command_artifact['cmd']](*command_artifact['args'], responses)
        for response in responses:
            if len(responses) == 1 or responses.count(response) > len(responses) / 2 + .1:
                Logger.electrum.debug('ConnectrumClient - resolve_cmd, response: %s', response)
                return response
        return self._resolve_cmd(command_artifact, retry + 1)

    def _update_status(self, status):
        if status != self._current_status:
            Logger.electrum.debug('ConnectrumClient - update_status (old: %s, new %s)', self._current_status, status)
            self._status_queue.queue.clear()
            self._status_queue.put_nowait(status)
            self._current_status = status

    def _electrum_disconnect(self):
        self._keepalive = False

    async def connect(self, cmdq, resq, statusq):
        Logger.electrum.debug('ConnectrumClient - connect')
        self._status_queue = statusq
        self._update_status('s')
        while 1:
            if not self._keepalive:
                for peer in self._peers:
                    peer.close()
                break

            if len(self._peers) < self.concurrency * self._connections_concurrency_ratio:
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
                        self._update_status('p, %s' % len(self._peers))
                        Logger.electrum.debug('ConnectrumClient - added peer %s:%s', _server[0], _server[1])
                except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
                    self.blacklisted.append(_server)
            else:
                self._update_status('c, %s' % len(self._peers))
            try:
                cmd = cmdq.get_nowait()
                if cmd:
                    try:
                        response = await self._resolve_cmd(cmd)
                        resq.put({'response': response}, timeout=3)
                    except RecursionError as e:
                        resq.put({'error': str(e)}, timeout=3)
            except queue.Empty:
                time.sleep(0.05)

    def _pick_peers(self):
        i = 0
        peers = []
        while 1:
            i += 1
            if i > 100:
                break
            peer = random.choice(self._peers)
            peer not in peers and peers.append(peer)
            if len(peers) == self.concurrency:
                break
        return peers

    async def _electrum_getrawtransaction(self, txid: str, responses):
        futures = [
            peer.RPC('blockchain.transaction.get', txid) for peer in self._pick_peers()
        ]
        for response in await asyncio.gather(*futures):
            response and responses.append(response)

    async def _electrum_getaddresshistory(self, scripthash: str, responses):
        futures = [
            peer.RPC('blockchain.address.get_history', scripthash) for peer in self._pick_peers()
        ]
        try:
            for response in await asyncio.gather(*futures):
                response and responses.append(response)
        except ElectrumErrorResponse as e:
            return

    async def _electrum_getblockheader(self, scripthash: str, responses):
        futures = [
            peer.RPC('blockchain.block.get_header', scripthash) for peer in self._pick_peers()
        ]
        for response in await asyncio.gather(*futures):
            response and responses.append(response)

    def _call(self, payload):
        self._cmd_queue.put(payload, timeout=2)
        try:
            response = self._res_queue.get(timeout=5)
        except queue.Empty:
            return
        if response.get('error'):
            return
        return response

    def _get_address_history(self, address):
        payload = {
            'cmd': 'getaddresshistory',
            'args': [address]
        }
        response = self._call(payload)
        return response

    def _get_block_header(self, height: int):
        payload = {
            'cmd': 'getblockheader',
            'args': [height]
        }
        response = self._call(payload)
        return response
