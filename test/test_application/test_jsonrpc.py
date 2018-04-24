import asyncio
from unittest import TestCase
from unittest.mock import Mock
from spruned.application.jsonrpc_server import JSONRPCServer
from spruned.application.utils.jsonrpc_client import JSONClient
from test.utils import async_coro


class TestJSONRPCServer(TestCase):
    def setUp(self):
        self.sut = JSONRPCServer('127.0.0.1', 31337, 'testuser', 'testpassword')
        self.vo_service = Mock()
        self.sut.set_vo_service(self.vo_service)
        self.client = JSONClient(b'testuser', b'testpassword', '127.0.0.1', 31337)
        self.loop = asyncio.get_event_loop()

    def test_getblockheader_success(self):
        response = {'block': 'header'}
        self.vo_service.getblockheader.return_value = async_coro(response)

        async def test():
            self.loop.create_task(self.sut.start())
            await asyncio.sleep(2)
            response = await self.client.call('getblockheader', '00'*32)
            print(response)
            await self.sut.stop()
        self.loop.run_until_complete(test())

    def test_getblockheader_error_missing(self):
        pass

    def test_getblockheader_error_params(self):
        pass

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
