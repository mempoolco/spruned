import asyncio
import random
from unittest import TestCase
from unittest.mock import Mock, call
from spruned.application.jsonrpc_server import JSONRPCServer
from spruned.application.utils.jsonrpc_client import JSONClient
from test.utils import async_coro


class TestJSONRPCServerSendrawtransaction(TestCase):
    def setUp(self):
        bindport = random.randint(11337, 41337)
        self.sut = JSONRPCServer('127.0.0.1', bindport, 'testuser', 'testpassword')
        self.vo_service = Mock()
        self.sut.set_vo_service(self.vo_service)
        self.client = JSONClient(b'testuser', b'testpassword', '127.0.0.1', bindport)
        self.loop = asyncio.get_event_loop()

    def test_sendrawtransaction_success(self):
        self.vo_service.sendrawtransaction.side_effect = [
            async_coro('bedf6b43cf9a9278b8637d89f378a8f25b8f0e1be729325f7eea74a3096d9520')
            ]

        async def test():
            await self.sut.start()
            response = await self.client.call('sendrawtransaction', params=['cafebabe'])
            return response

        res = self.loop.run_until_complete(test())
        self.assertEqual(
            res,
            {
                'error': None, 'id': 1, 'jsonrpc': '2.0',
                'result': 'bedf6b43cf9a9278b8637d89f378a8f25b8f0e1be729325f7eea74a3096d9520'
             }
        )

    def test_getrawtransaction_error_decode(self):
        async def test():
            await self.sut.start()
            response = await self.client.call('sendrawtransaction', params=["nonhex"])
            return response

        res = self.loop.run_until_complete(test())
        self.assertEqual(
            res,
            {'error': {'code': -22, 'message': 'TX decode failed'},
             'id': 1,
             'jsonrpc': '2.0',
             'result': None}
        )
        Mock.assert_not_called(self.vo_service.getblock)
