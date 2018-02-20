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
    def __init__(self, coin, loop, concurrency=5):
        self.loop = loop
        assert coin == settings.Network.BITCOIN
        self.connections = []
        self.concurrency = concurrency
        self.blacklisted = []
        self._keepalive = True
        self._cmd_queue = None  # type: queue.Queue
        self._res_queue = None  # type: queue.Queue

    def killpill(self):
        self._keepalive = False

    def connect(self):
        self._cmd_queue = queue.Queue()
        self._res_queue = queue.Queue()
        t = threading.Thread(target=loop.run_until_complete, args=[self._connect(self._cmd_queue, self._res_queue)])
        t.start()

    async def _resolve_cmd(self, command_artifact):
        cmds = {
            'getrawtransaction': self._getrawtransaction_frompool
        }
        response = []
        await cmds[command_artifact['cmd']](*command_artifact['args'], response)
        return response

    async def _connect(self, cmdq, resq):
        while 1:
            try:
                cmd = cmdq.get_nowait()
                if cmd:
                    res = await self._resolve_cmd(cmd)
                    resq.put(res)
            except queue.Empty:
                pass

            if not self._keepalive:
                for connection in self.connections:
                    connection.close()
                break

            if len(self.connections) < self.concurrency:
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

    async def _getrawtransaction_frompool(self, txid: str, responses):
        futures = [
            connection.RPC('blockchain.transaction.get', txid) for connection in self.connections
        ]
        for response in await asyncio.gather(*futures):
            response and responses.append(response)

    def getrawtransaction(self, txid: str):
        cmd = {
            'cmd': 'getrawtransaction',
            'args': [txid]
        }

        self._cmd_queue.put(cmd)
        return self._res_queue.get(timeout=3)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    electrum = ConnectrumService(settings.NETWORK, loop, concurrency=5)
    electrum.connect()
    finished = False
    while not finished:
        if electrum.concurrency > len(electrum.connections):
            print('not enough connections: %s'.format(len(electrum.connections)))
            time.sleep(5)
        else:
            res = electrum.getrawtransaction('5029394b46e48dfdcf2eaf0bbaad97735a7fa44f2cf51007aa69584c2476fb27')
            print([x for x in res])
            finished = True
    electrum.killpill()
