import unittest
from unittest.mock import Mock

from spruned.application.spruned_vo_service import SprunedVOService


class TestVOService(unittest.TestCase):
    def setUp(self):
        self.electrod = Mock()
        self.cache = Mock()
        self.utxo_tracker = Mock()
        self.repository = Mock()

        self.sut = SprunedVOService(self.electrod, self.cache, self.utxo_tracker, self.repository)

    def tearDown(self):
        self.electrod.reset_mock()
        self.cache.reset_mock()
        self.utxo_tracker.reset_mock()
        self.repository.reset_mock()

