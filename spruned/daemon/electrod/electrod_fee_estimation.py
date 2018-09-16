import asyncio
import json
import random
import time
from statistics import median
from spruned.daemon.electrod.electrod_connection import ElectrodConnection


class NotEnoughDataException(Exception):
    pass


class NoPeersException(Exception):
    pass


class EstimateFeeConsensusProjector:
    def __init__(self, distance=0.1, time_window=900, max_age=120):
        self._max_age = max_age
        self._time_window = time_window
        self._d = distance

    def _produce_projection(self, data, p, agreement):
        response = {
            "agreement": 0,
            "points": [entry["value"] for entry in data],
            "median": 0,
            "average": 0,
            "timestamp": median([entry["timestamp"] for entry in data]),
            "disagree": [],
        }
        med = response["median"] = median(response["points"])

        def evaluate_value(_v):
            return bool(med - med*self._d < _v < med + med*self._d)

        perc = int(100 / p)
        agreed = []
        for entry in data:
            if evaluate_value(entry["value"]):
                response["agreement"] += perc
                agreed.append(entry["value"])
            else:
                response["disagree"].append(entry["peer"])
        response["agree"] = (response["agreement"] >= agreement)
        response["average"] = int(sum(agreed) / len(agreed))
        return response

    def project(self, data, members, agreement=80):
        evaluate = []
        now = int(time.time())
        print('Projecting data: %s (%s)' % (data, len(data)))
        for d in data:
            if self._max_age + d["timestamp"] > now:
                evaluate.append(d)
        if len(evaluate) >= members:
            return self._produce_projection(data, members, agreement)
        raise NotEnoughDataException


class EstimateFeeConsensusCollector:
    def __init__(self, connectionclass=ElectrodConnection, time_window=120, max_age=900):
        self._rates = set()
        self._data = dict()
        self._time_window = time_window
        self._permanent_connections_pool = None
        self._connectionclass = connectionclass
        self._peers = set()
        self._max_age = max_age

    def add_peer(self, peer):
        self._peers.add(peer)

    def add_permanent_connections_pool(self, connectionpool):
        self._permanent_connections_pool = connectionpool

    def to_json(self):
        return {
            "data": self._data,
            "max_age": self._max_age
        }

    @classmethod
    def from_json(cls, data) -> 'EstimateFeeConsensusCollector':
        i = cls()
        i._data = data["data"]
        i._max_age = data["max_age"]
        return i

    def add_peer_to_consensus(self, *peers):
        for peer in peers:
            if self._data.get(peer):
                pass
            self._data[peer] = {
                "rates": {r: None for r in self._rates},
                "peer": peer,
                "score": 0
            }

    def add_rate(self, *rate):
        diff = set(rate) - self._rates
        if diff:
            self._rates = self._rates | diff
        for newrate in diff:
            for peer in self._data:
                self._data[peer]["rates"][newrate] = None

    def _add_collected_rate_to_data(self, peer, rate, value, timestamp=None):
        self._data[peer]["rates"][rate] = [value, timestamp or int(time.time())]

    async def collect(self, rates=None, members=8):
        _ = rates and [self.add_rate(rate) for rate in rates if rate not in self._rates]
        if not self.is_consensus_pool_established(members):
            self._establish_consensus_pool(members)
        expired_peers = self.get_expired_consensus_members()
        print('Expird peers: %s' % expired_peers)
        if expired_peers:
            futures = []
            connections = []
            for peer in expired_peers:
                hostname, protocol = peer.split('/')
                connection = self._connectionclass(hostname, protocol, keepalive=False, timeout=5)
                if self._is_active(self._data[peer]) and not self._is_updated(self._data[peer], rates):
                    futures.append(self._update(peer, connection, rates))
                    if futures:
                        try:
                            print('Connecting to %s' % hostname)
                            await connection.connect()
                            connections.append(connection)
                        except:
                            self.penalize_peer(peer)
            await asyncio.gather(*futures, return_exceptions=True)
            for connection in connections:
                try:
                    await connection.disconnect()
                except:
                    pass

    def _establish_consensus_pool(self, members):
        while not self.is_consensus_pool_established(members):
            if not self._peers:
                raise NoPeersException
            peer = self._peers.pop()
            self.add_peer_to_consensus(peer)

    def is_consensus_pool_established(self, members):
        if len(self._data) < members:
            return False
        active = []
        for peer, value in self._data.items():
            if self._is_active(value):
                active.append(peer)
        return len(active) >= members

    def get_expired_consensus_members(self, rates=None):
        expired = []
        for peer, value in self._data.items():
            if not self._is_updated(value, rates) and self._is_active(value):
                expired.append(peer)
        return expired

    def _is_active(self, peer):
        return peer['score'] >= 0

    def _is_rate_expired(self, rate):
        now = int(time.time())
        if rate is None or (now > rate["timestamp"] + self._max_age):
            return True

    def _is_updated(self, peer, rates):
        if rates is not None:
            print(peer)
            container = {k: v for k, v in peer["rates"].items() if k in rates}.items()
        else:
            container = peer["rates"].items()
        for rate, value in container:
            if self._is_rate_expired(value):
                return False
        return True

    def penalize_peer(self, peer):
        self._data[peer]["score"] -= 1

    def reward_peer(self, peer):
        self._data[peer]["score"] += 1

    async def _update(self, peer, connection, rates=None):
        futures = []

        async def estimatefee(peer, conn, target):
            res = await conn.client.RPC("blockchain.estimatefee", str(target))
            if not res:
                return
            return {
                "target": target,
                "peer": peer,
                "value": int((float(res) * 10**8)/1000)
            }
        if rates is not None:
            container = {k: v for k, v in self._data[peer]["rates"].items() if k in rates}.items()
        else:
            container = self._data[peer]["rates"].items()
        for rate, value in container:
            if self._is_rate_expired(value):
                futures.append(estimatefee(peer, connection, rate))

        if connection:
            try:
                results = await asyncio.gather(*futures, return_exceptions=True)
                for result in results:
                    if result and not isinstance(result, Exception):
                        print('Received result: %s' % result)
                        self._data[result["peer"]]["rates"][result["target"]] = {
                            "value": result["value"],
                            "timestamp": int(time.time()),
                            "peer": result["peer"],
                            "target": result["target"]
                        }
                        print('Result saved: %s' % self._data[result["peer"]]["rates"][result["target"]])
                        self.reward_peer(peer)
                    else:
                        self.penalize_peer(peer)
            except Exception as e:
                self.penalize_peer(peer)
                print('DIOMERDA: %s' % e)
                raise e

    def rates_available(self, consensus):
        data = []
        for peer, peerdata in self._data.items():
            data.append(self._is_updated(peerdata, self._rates))
        if len([x for x in data if x]) >= consensus:
            return True

    def get_data(self, rates=None):
        return [data for _, data in self._data.items() if self._is_updated(data, rates) and self._is_active(data)]

    def get_jsondata(self, rates=None):
        return json.dumps(self.get_data(rates), indent=2)

    def get_rates(self, *value):
        data = []
        for v in value:
            assert v in self._rates
            data.extend([x["rates"][v] for x in self.get_data([v])])
        return data


if __name__ == '__main__':
    p = [

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
        ["gh05.geekhosters.com", "s"],
        ["electrum-1.mempool.co", "s"]

    ]
    l = asyncio.get_event_loop()
    e = EstimateFeeConsensusCollector()
    peers = [x[0] + '/' + x[1] for x in p]
    random.shuffle(peers)
    for _p in peers:
        e.add_peer(_p)
    p = EstimateFeeConsensusProjector()
    RATES = [1]
    CONSENSUS_MEMBERS = 3
    start = int(time.time())
    print('Requesting data')
    while 1:
        l.run_until_complete(e.collect(rates=RATES, members=CONSENSUS_MEMBERS))
        if not len(e.get_rates(*RATES)) >= CONSENSUS_MEMBERS:
            continue
        rates_data = e.get_rates(*RATES)
        projection = p.project(rates_data, members=CONSENSUS_MEMBERS)
        for d in projection["disagree"]:
            _ = [e.penalize_peer(d) for _ in range(0, 5)]
        if projection["agree"]:
            print(projection)
            print('Data obtained in %s' % (int(time.time()) - start))
            break
        else:
            continue