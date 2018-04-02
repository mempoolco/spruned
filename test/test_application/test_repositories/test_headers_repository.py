import unittest

from spruned import settings
from spruned.repositories.headers_repository import HeadersSQLiteRepository
from spruned.application.database import sqlite
from spruned.daemon import exceptions
from test.utils import make_headers


class TestHeadersRepository(unittest.TestCase):
    def setUp(self):
        assert not settings.SQLITE_DBNAME
        self.sut = HeadersSQLiteRepository(sqlite)

    def tests_headers_repository_ok(self):
        """
        all the successful headers repository calls can be made.
        """
        self.sut.remove_headers_after_height(0)
        headers = make_headers(0, 5, with_timestamp=False)
        res = self.sut.save_header(
            headers[0]['block_hash'],
            headers[0]['block_height'],
            headers[0]['header_bytes'],
            None
        )
        self.assertEqual(res, headers[0])
        self.sut.save_headers(headers[1:])
        best_header = self.sut.get_best_header()
        self.assertEqual(best_header, headers[-1])
        self.assertEqual(self.sut.get_header_at_height(4), headers[4])
        self.assertEqual(self.sut.get_block_hash(3), headers[3]['block_hash'])
        self.assertEqual(self.sut.get_block_height(headers[3]['block_hash']), 3)
        header3 = self.sut.get_header_at_height(3)
        self.assertEqual(header3.pop('next_block_hash'), headers[4]['block_hash'])
        self.assertEqual(header3, headers[3])

        headers2 = make_headers(5, 10, with_timestamp=False, prevblock_0=headers[4]['block_hash'])

        res = self.sut.save_header(
            headers2[0]['block_hash'],
            headers2[0]['block_height'],
            headers2[0]['header_bytes'],
            headers2[0]['prev_block_hash']
        )
        self.assertEqual(res, headers2[0])
        self.sut.save_headers(headers2[1:])
        self.assertEqual(self.sut.get_best_header(), headers2[-1])

        self.sut.remove_headers_after_height(headers2[0]['block_height'])
        self.assertEqual(self.sut.get_best_header(), headers[-1])

        self.sut.save_headers(headers2)
        self.assertEqual(self.sut.get_best_header(), headers2[-1])

        self.sut.remove_header_at_height(headers2[-1]['block_height'])
        res = self.sut.save_header(
            headers2[-1]['block_hash'],
            headers2[-1]['block_height'],
            headers2[-1]['header_bytes'],
            headers2[-1]['prev_block_hash']
        )
        self.assertEqual(res, headers2[-1])
        self.assertEqual(self.sut.get_best_header(), headers2[-1])

        res = self.sut.get_headers_since_height(headers2[3]['block_height'])
        self.assertEqual(res[0].pop('next_block_hash'), headers2[4]['block_hash'])
        self.assertEqual(headers2[3:], res)

    def test_headers_repository_save_wrong_headers(self):
        self.sut.remove_headers_after_height(0)
        headers = make_headers(0, 5, with_timestamp=False)
        res = self.sut.save_header(
            headers[0]['block_hash'],
            headers[0]['block_height'],
            headers[0]['header_bytes'],
            None
        )
        self.assertEqual(res, headers[0])
        self.sut.save_headers(headers[1:])
        headers2 = make_headers(5, 6, with_timestamp=False, prevblock_0=headers[3]['block_hash'])
        with self.assertRaises(exceptions.HeadersInconsistencyException):
            self.sut.save_header(
                headers2[0]['block_hash'],
                headers2[0]['block_height'],
                headers2[0]['header_bytes'],
                headers2[0]['prev_block_hash']
            )
