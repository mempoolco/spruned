import json
import unittest
from unittest.mock import ANY, Mock
import asyncio
import time
from spruned.dependencies.connectrum import ServerInfo, StratumClient
from test.utils import async_coro


class TestServerInfo(unittest.TestCase):
    def setUp(self):
        pass

    def test_serverinfo(self):
        sut = ServerInfo('cafebabe', 'localhost', 's', version='1.2', pruning_limit=1000, ip_addr='127.0.0.1')
        server_dict = {'nickname': 'cafebabe', 'hostname': 'localhost', 'ip_addr': '127.0.0.1',
                         'local_version': '1.2', 'ports': ['s'], 'version': '1.2', 'pruning_limit': 1000
                       }
        d = {k:v for k,v in server_dict.items()}
        d.update({'seen_at': ANY})
        self.assertEqual(dict(sut), d)
        server_info = ServerInfo.from_dict(server_dict)
        self.assertEqual(str(server_info), 'localhost')
        self.assertEqual(server_info.protocols, {'s'})
        self.assertEqual(server_info.hostname, 'localhost')
        self.assertEqual(server_info.pruning_limit, 1000)
        self.assertEqual(server_info.is_onion, False)


class TestStratumClient(unittest.TestCase):
    def setUp(self):
        server_dict = {
            'nickname': 'cafebabe', 'hostname': 'localhost', 'ip_addr': '127.0.0.1',
            'local_version': '1.2', 'ports': ['t'], 'version': '1.2', 'pruning_limit': 1000}
        self.mock_loop = Mock()
        self.sut = StratumClient()
        self.server_info = ServerInfo.from_dict(server_dict)
        self.loop = asyncio.get_event_loop()

    def test_connection_error(self):
        transport, protocol = Mock(), Mock()
        self.mock_loop.create_connection.return_value = async_coro((transport, protocol))

        with self.assertRaises(ConnectionRefusedError) as e:
            self.loop.run_until_complete(
                self.sut.connect(self.server_info)
            )

    def _setup_electrum_server(self, server_info):
        async def methods(r, w):
            responses = {
                'server.version': 'mock 1.2 1.2',
                'blockchain.scripthash.listunspent': 'cafebabe',
                'something.subscribe': 'babe',
                'server.ping': True
            }
            while 1:
                data = await r.read(1024)
                if not data:
                    w.close()
                    break
                else:
                    d = json.loads(data.strip().decode())
                    command = d['method']
                    response = {'result': responses[command], 'id': d['id']}
                    res = json.dumps(response) + '\n'
                    w.write(res.encode())
                    await w.drain()

        host = server_info.hostname
        coro = asyncio.start_server(methods, host=host, port=50001, loop=self.loop)
        return coro

    def test_connection_successful(self):
        async def test():
            done = False

            server = await self._setup_electrum_server(self.server_info)
            await asyncio.sleep(1)
            await self.sut.connect(self.server_info)
            self.sut.subscribe('something.subscribe', ['cafe'])
            start = int(time.time())
            while not done:
                if int(time.time()) - start > 5:
                    raise ValueError('Test is stuck')
                await asyncio.sleep(1)
                if self.sut.protocol:
                    self.sut.close()
                    done = True
                    server.close()

        self.loop.run_until_complete(test())
