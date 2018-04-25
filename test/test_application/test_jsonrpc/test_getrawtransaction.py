import asyncio
import random
from unittest import TestCase
from unittest.mock import Mock, call
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

    def test_getrawtransaction_success(self):
        pass

    def test_getrawtransaction_error_missing(self):
        pass

    def test_getrawtransaction_error_params(self):
        pass

