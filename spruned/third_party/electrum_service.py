import asyncio

from async_timeout import timeout
from connectrum.client import StratumClient
from connectrum.svr_info import ServerInfo
from spruned import settings
import random
import logging
import sys
import binascii
import os

root = logging.getLogger()
root.setLevel(logging.DEBUG)

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
root.addHandler(ch)


class ConnectrumService:
    def __init__(self, coin, concurrency=5):
        assert coin == settings.Network.BITCOIN
        self.connections = []
        self.concurrency = concurrency
        self.blacklisted = []

    async def connect(self):
        while len(self.connections) < self.concurrency:
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
                    self.connections.append(conn)
            except (ConnectionRefusedError, asyncio.TimeoutError):
                self.blacklisted.append(_server)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    server = ConnectrumService(settings.NETWORK)
    loop.run_until_complete(server.connect())
