import asyncio
import queue
import time
from async_timeout import timeout
from connectrum.client import StratumClient
from connectrum.svr_info import ServerInfo
from spruned import settings
import random
import logging
import sys
import binascii
import os
import threading


root = logging.getLogger()
root.setLevel(logging.DEBUG)

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
root.addHandler(ch)


class ConnectrumService:
    def __init__(self, coin, loop, concurrency=5, max_retries_on_discordancy=5, connections_concurrency_ratio=5):
        self.loop = loop
        assert coin == settings.Network.BITCOIN
        self.connections = []
        self.concurrency = concurrency
        self.blacklisted = []
        self._keepalive = True
        self._cmd_queue = None  # type: queue.Queue
        self._res_queue = None  # type: queue.Queue
        self._max_retries_on_discordancy = max_retries_on_discordancy
        self._connections_concurrency_ratio = connections_concurrency_ratio


    def killpill(self):
        self._keepalive = False

    def connect(self):
        self._cmd_queue = queue.Queue(maxsize=1)
        self._res_queue = queue.Queue(maxsize=1)
        t = threading.Thread(
            target=loop.run_until_complete, args=[self._connect(self._cmd_queue, self._res_queue)]
        )
        t.start()

    async def _resolve_cmd(self, command_artifact, retry=0):
        if retry >= self._max_retries_on_discordancy:
            raise RecursionError
        cmds = {
            'getrawtransaction': self._getrawtransaction_frompool
        }
        responses = []
        await cmds[command_artifact['cmd']](*command_artifact['args'], responses)
        for response in responses:
            if responses.count(response) > len(responses) / 2 + .1:
                return response
        return self._resolve_cmd(command_artifact, retry + 1)

    async def _connect(self, cmdq, resq):
        while 1:
            try:
                cmd = cmdq.get_nowait()
                if cmd:
                    try:
                        response = await self._resolve_cmd(cmd)
                        resq.put({'response': response})
                    except RecursionError as e:
                        resq.put({'error': str(e)})
            except queue.Empty:
                pass

            if not self._keepalive:
                for connection in self.connections:
                    connection.close()
                break

            if len(self.connections) < self.concurrency * self._connections_concurrency_ratio:
                _server = None
                i = 0
                while not _server:
                    i += 1
                    _server = random.choice(settings.ELECTRUM_SERVERS)
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
                        banner and self.connections.append(conn)
                        banner and logging.debug('Connected to %s, banner', _server[0])
                except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
                    self.blacklisted.append(_server)

    def _pick_connections(self):
        i = 0
        connections = []
        while 1:
            i += 1
            if i > 100:
                break
            connection = random.choice(self.connections)
            connection not in connections and connections.append(connection)
            if len(connections) == self.concurrency:
                break
        return connections

    async def _getrawtransaction_frompool(self, txid: str, responses):
        futures = [
            connection.RPC('blockchain.transaction.get', txid) for connection in self._pick_connections()
        ]
        for response in await asyncio.gather(*futures):
            response and responses.append(response)

    def getrawtransaction(self, txid: str, retry=0):
        if retry > 3:
            raise ValueError
        payload = {
            'cmd': 'getrawtransaction',
            'args': [txid]
        }
        self._cmd_queue.put(payload)
        try:
            response = self._res_queue.get(timeout=5)
        except queue.Empty:
            return
        if response.get('error'):
            return
        return response['response']


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    electrum = ConnectrumService(settings.NETWORK, loop, concurrency=3)
    electrum.connect()
    finished = False
    while not finished:
        if electrum.concurrency > len(electrum.connections):
            print('not enough connections: %s'.format(len(electrum.connections)))
            time.sleep(5)
        else:
            res = electrum.getrawtransaction('5029394b46e48dfdcf2eaf0bbaad97735a7fa44f2cf51007aa69584c2476fb27')
            print(res)
            finished = True
    electrum.killpill()