import asyncio
import random
from unittest import TestCase
from unittest.mock import Mock, call

from spruned.application.exceptions import ItemNotFoundException
from spruned.application.jsonrpc_server import JSONRPCServer
from spruned.application.utils.jsonrpc_client import JSONClient
from spruned.daemon import exceptions
from test.utils import async_coro


class TestJSONRPCServerGetrawtransaction(TestCase):
    def setUp(self):
        bindport = random.randint(31337, 41337)
        self.sut = JSONRPCServer('127.0.0.1', bindport, 'testuser', 'testpassword')
        self.vo_service = Mock()
        self.sut.set_vo_service(self.vo_service)
        self.client = JSONClient(b'testuser', b'testpassword', '127.0.0.1', bindport)
        self.loop = asyncio.get_event_loop()

    def test_getrawtransaction_success(self):
        self.vo_service.getrawtransaction.side_effect = [async_coro('cafebabe')]

        async def test():
            await self.sut.start()
            response = await self.client.call('getrawtransaction', params=['00' * 32])
            response2 = await self.client.call('getrawtransaction', params=['00' * 32, True])
            return response, response2

        res, res2 = self.loop.run_until_complete(test())
        self.assertEqual(
            res,
            {'error': None, 'id': 1, 'jsonrpc': '2.0', 'result': 'cafebabe'}
        )
        Mock.assert_has_calls(
            self.vo_service.getrawtransaction,
            calls=[
                call('00' * 32, False)
            ]
        )

    def test_getrawtransaction_error_missing(self):
        self.vo_service.getrawtransaction.side_effect = ItemNotFoundException

        async def test():
            await self.sut.start()
            response = await self.client.call('getrawtransaction', params=['00' * 32])
            return response

        res = self.loop.run_until_complete(test())
        self.assertEqual(
            res,
            {
                'error': {'code': -5,
                          'message': 'No such mempool or blockchain transaction. [maybe try again]'
                          },
                'id': 1,
                'jsonrpc': '2.0',
                'result': None
            }
        )

    def test_getrawtransaction_error_params(self):
        response = None
        self.vo_service.getrawtransaction.return_value = async_coro(response)

        async def test():
            await self.sut.start()
            response1 = await self.client.call('getrawtransaction', params=['wrong_hash'])
            response2 = await self.client.call('getrawtransaction', params=['cafebabe'])
            return response1, response2

        res, res2 = self.loop.run_until_complete(test())
        self.assertEqual(
            res,
            {'error': {'code': -8,
                       'message': 'parameter 1 must be hexadecimal string (not '
                                  "'wrong_hash')"},
             'id': 1,
             'jsonrpc': '2.0',
             'result': None}
        )
        self.assertEqual(
            res2,
            {'error': {'code': -8, 'message': "parameter 1 must be of length 64 (not '8')"},
             'id': 1,
             'jsonrpc': '2.0',
             'result': None}
        )
        Mock.assert_not_called(self.vo_service.getblockheader)

    def test_getrawtransaction_error_genesis(self):
        self.vo_service.getrawtransaction.side_effect = exceptions.GenesisTransactionRequestedException

        async def test():
            await self.sut.start()
            response1 = await self.client.call(
                'getrawtransaction',
                params=[
                    '000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f'
                ])
            return response1

        res = self.loop.run_until_complete(test())
        self.assertEqual(
            res,
            {'error': {'code': -5,
                       'message': 'The genesis block coinbase is not considered an '
                                  'ordinary transaction and cannot be retrieved'
                       },
             'id': 1,
             'jsonrpc': '2.0',
             'result': None}
        )

