import asyncio
import random
from unittest import TestCase
from unittest.mock import Mock, call
from spruned.application.jsonrpc_server import JSONRPCServer
from spruned.application.utils.jsonrpc_client import JSONClient
from test.utils import async_coro


class TestJSONRPCServerGetblockheader(TestCase):
    def setUp(self):
        bindport = self.bindport = random.randint(31337, 41337)
        self.sut = JSONRPCServer('127.0.0.1', bindport, 'testuser', 'testpassword')
        self.vo_service = Mock()
        self.sut.set_vo_service(self.vo_service)
        self.client = JSONClient(b'testuser', b'testpassword', '127.0.0.1', bindport)
        self.loop = asyncio.get_event_loop()

    def test_auth_failed(self):
        client = JSONClient(b'testuser', b'testpassworda', '127.0.0.1', self.bindport)

        async def test():
            await self.sut.start()
            response = await client.call('getblockheader', params=['00'*32])
            return response

        res = self.loop.run_until_complete(test())
        self.assertEqual(res, {})
        Mock.assert_not_called(self.vo_service.getblockheader)

    def test_echo(self):
        async def test():
            await self.sut.start()
            response = await self.client.call('echo')
            return response

        res = self.loop.run_until_complete(test())
        self.assertEqual(res, {'id': 1, 'result': '', 'error': None, 'jsonrpc': '2.0'})

    def test_help(self):
        async def test():
            await self.sut.start()
            response = await self.client.call('help')
            return response

        res = self.loop.run_until_complete(test())
        self.assertIsNotNone(res)

    def test_getblockheader_success(self):
        self.vo_service.getblockheader.side_effect = [async_coro({'block': 'header'}),
                                                      async_coro('cafebabe')]
        async def test():
            await self.sut.start()
            response = await self.client.call('getblockheader', params=['00'*32])
            response2 = await self.client.call('getblockheader', params=['00'*32, False])
            return response, response2

        res, res2 = self.loop.run_until_complete(test())
        self.assertEqual(
            res,
            {'error': None, 'id': 1, 'jsonrpc': '2.0', 'result': {'block': 'header'}}
        )
        self.assertEqual(
            res2,
            {'error': None, 'id': 1, 'jsonrpc': '2.0', 'result': 'cafebabe'}
        )
        Mock.assert_has_calls(
            self.vo_service.getblockheader,
            calls=[
                call('00' * 32, verbose=True),
                call('00' * 32, verbose=False)
            ]
        )

    def test_getblockheader_error_missing(self):
        response = None
        self.vo_service.getblockheader.return_value = async_coro(response)

        async def test():
            await self.sut.start()
            response = await self.client.call('getblockheader', params=['00'*32])
            return response

        res = self.loop.run_until_complete(test())
        self.assertEqual(
            res,
            {'error': {'code': -5, 'message': 'Block not found'}, 'id': 1, 'jsonrpc': '2.0', 'result': None}
        )
        Mock.assert_called_with(self.vo_service.getblockheader, '00' * 32, verbose=True)

    def test_getblockheader_error_params(self):
        response = None
        self.vo_service.getblockheader.return_value = async_coro(response)

        async def test():
            await self.sut.start()
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

        # Really should be code: -32602, but that'll cause bitcoin-cli not to
        # error out correctly, so we use -1 instead
        self.assertEqual(
            res2,
            {'jsonrpc': '2.0', 'error': {'code': -1, 'message': 'Invalid params'}, 'id': 1, 'result': None}
        )
        Mock.assert_not_called(self.vo_service.getblockheader)
