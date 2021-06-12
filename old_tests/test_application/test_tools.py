import unittest
from unittest.mock import Mock

from spruned.application.database import erase_ldb_storage
from spruned.application.tools import inject_attribute


class TestTools(unittest.TestCase):
    def test_injection(self):
        fn = lambda: True
        o1 = Mock()
        o2 = Mock()
        inject_attribute(fn, 'spruned', o1, o2)
        self.assertEqual(o1.spruned, fn)
        self.assertEqual(o2.spruned, fn)

    def test_erase_leveldb(self):
        with self.assertRaises(ValueError):
            erase_ldb_storage()
