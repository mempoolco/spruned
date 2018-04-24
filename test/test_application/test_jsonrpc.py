import asyncio
import random
from unittest import TestCase
from unittest.mock import Mock
from spruned.application.jsonrpc_server import JSONRPCServer
from spruned.application.utils.jsonrpc_client import JSONClient
from test.utils import async_coro


class TestJSONRPCServer(TestCase):
    def setUp(self):
        bindport = random.randint(31337, 41337)
        self.sut = JSONRPCServer('127.0.0.1', bindport, 'testuser', 'testpassword')
        self.vo_service = Mock()
        self.sut.set_vo_service(self.vo_service)
        self.client = JSONClient(b'testuser', b'testpassword', '127.0.0.1', bindport)
        self.loop = asyncio.get_event_loop()

    def test_getblockheader_success(self):
        response = {'block': 'header'}
        self.vo_service.getblockheader.return_value = async_coro(response)

        async def test():
            self.loop.create_task(self.sut.start())
            await asyncio.sleep(1)
            response = await self.client.call('getblockheader', params=['00'*32])
            return response

        res = self.loop.run_until_complete(test())
        self.assertEqual(
            res,
            {'error': None, 'id': 1, 'jsonrpc': '2.0', 'result': {'block': 'header'}}
        )

    def test_getblockheader_error_missing(self):
        response = None
        self.vo_service.getblockheader.return_value = async_coro(response)

        async def test():
            self.loop.create_task(self.sut.start())
            await asyncio.sleep(1)
            response = await self.client.call('getblockheader', params=['00'*32])
            return response

        res = self.loop.run_until_complete(test())
        self.assertEqual(
            res,
            {'error': {'code': -5, 'message': 'Block not found'}, 'id': 1, 'jsonrpc': '2.0', 'result': None}
        )

    def test_getblockheader_error_params(self):
        response = None
        self.vo_service.getblockheader.return_value = async_coro(response)

        async def test():
            self.loop.create_task(self.sut.start())
            await asyncio.sleep(1)
            response1 = await self.client.call('getblockheader', params=['wrong_blockhash'])
            response2 = await self.client.call('getblockheader')
            return response1, response2

        res, res2 = self.loop.run_until_complete(test())
        self.assertEqual(
            res,
            {
                'jsonrpc': '2.0',
                'error': {
                    'code': -5, 'message': 'Error parsing JSON:wrong_blockhash'
                },
                'id': 1,
                'result': None
            }
        )
        self.assertEqual(
            res2,
            {'jsonrpc': '2.0', 'error': {'code': -32602, 'message': 'Invalid params'}, 'id': 1, 'result': None}
        )

    def test_getblock_success(self):
        pass

    def test_getblock_error_missing(self):
        pass

    def test_getblock_error_params(self):
        pass

    def test_getrawtransaction_success(self):
        pass

    def test_getrawtransaction_error_missing(self):
        pass

    def test_getrawtransaction_error_params(self):
        pass
