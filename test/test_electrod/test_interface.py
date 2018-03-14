import asyncio
import unittest
from unittest.mock import Mock, create_autospec, call
import time

from spruned.application import settings
from spruned.application.abstracts import HeadersRepository
from spruned.daemon import exceptions
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from spruned.daemon.electrod.electrod_reactor import ElectrodReactor
from test.utils import async_coro, coro_call, in_range, make_headers
import warnings


class TestElectrodInterface(unittest.TestCase):
    def setUp(self):
        self.delay_task_runner = Mock()
        self.connectrum = Mock()
        self.electrod_loop = Mock()


