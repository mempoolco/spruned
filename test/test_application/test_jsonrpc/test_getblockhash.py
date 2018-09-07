import asyncio
import random
from unittest import TestCase
from unittest.mock import Mock, call
from spruned.application.jsonrpc_server import JSONRPCServer
from spruned.application.utils.jsonrpc_client import JSONClient
from test.utils import async_coro


class TestJSONRPCServerGetblock(TestCase):
    def setUp(self):
        bindport = random.randint(31337, 41337)
        self.sut = JSONRPCServer('127.0.0.1', bindport, 'testuser', 'testpassword')
        self.vo_service = Mock()
        self.sut.set_vo_service(self.vo_service)
        self.client = JSONClient(b'testuser', b'testpassword', '127.0.0.1', bindport)
        self.loop = asyncio.get_event_loop()

    def test_getblockhash_success(self):
        self.vo_service.getblockhash.side_effect = [async_coro('cafebabe')]

        async def test():
            await self.sut.start()
            response = await self.client.call('getblockhash', params=[1000])
            return response

        res = self.loop.run_until_complete(test())
        self.assertEqual(res, {'id': 1, 'result': 'cafebabe', 'error': None, 'jsonrpc': '2.0'})

        Mock.assert_has_calls(self.vo_service.getblockhash, calls=[call(1000)])

    def test_getblockhash_error_missing(self):
        response = None
        self.vo_service.getblockhash.return_value = async_coro(response)

        async def test():
            await self.sut.start()
            response = await self.client.call('getblockhash', params=[1000])
            return response

        res = self.loop.run_until_complete(test())
        self.assertEqual(
            res,
            {'error': {'code': -8, 'message': 'Block height out of range'},
             'id': 1,
             'jsonrpc': '2.0',
             'result': None}
        )
        Mock.assert_called_with(self.vo_service.getblockhash, 1000)

    def test_getblock_error_error_params(self):
        response = None
        self.vo_service.getblockhash.return_value = async_coro(response)

        async def test():
            await self.sut.start()
            response1 = await self.client.call('getblockhash', params=['non_int'])
            response2 = await self.client.call('getblockhash')
            return response1, response2

        res, res2 = self.loop.run_until_complete(test())
        self.assertEqual(
            res,
            {
                'jsonrpc': '2.0',
                'error': {
                    'code': -5, 'message': 'Error parsing JSON:non_int'
                },
                'id': 1,
                'result': None
            }
        )
        # Really should be code: -32602, but that'll cause bitcoin-cli not to
        # error out correctly, so we use -1 instead
        self.assertEqual(
            res2,
            {'jsonrpc': '2.0', 'error': {'code': -1, 'message': 'Invalid params'}, 'id': 1, 'result': None}
        )
        Mock.assert_not_called(self.vo_service.getblock)
