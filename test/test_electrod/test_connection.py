import asyncio
import unittest
from unittest.mock import Mock, create_autospec, call
import binascii

import time

from spruned.daemon.electrod.electrod_connection import ElectrodConnectionPool, ElectrodConnection
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon.exceptions import ElectrodMissingResponseException
from test.utils import async_coro


class TestElectrodConnection(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.sut = ElectrodConnection('hostname', 's', client=self.client, expire_errors_after=3)
        self.loop = asyncio.get_event_loop()

    def tearDown(self):
        self.client.reset_mock()

    def test_errors_score(self):
        self.loop.run_until_complete(
            asyncio.gather(
                self.sut.on_error('error1'),
                self.sut.on_error('error1'),
                self.sut.on_error('error1')
            )
        )
        self.assertEqual(self.sut.score, 7)
        time.sleep(3.01)
        self.assertEqual(self.sut.score, 10)
