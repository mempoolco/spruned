import unittest

import binascii

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
        headers = [
            {
                'block_hash': '000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f',
                'block_height': 0,
                'header_bytes': binascii.unhexlify(
                    '0100000000000000000000000000000000000000000000000000000000000000000000'
                    '003ba3edfd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a29ab5f49ffff001d1dac2b7c'
                ),
            },
            {
                'block_hash': '00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048',
                'block_height': 1,
                'header_bytes': binascii.unhexlify(

                    '010000006fe28c0ab6f1b372c1a6a246ae63f74f931e8365e15a089c68d6190000000000982051f'
                    'd1e4ba744bbbe680e1fee14677ba1a3c3540bf7b1cdb606e857233e0e61bc6649ffff001d01e36299'
                ),
                'prev_block_hash': '000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f'
            },
            {
                'block_hash': '000000006a625f06636b8bb6ac7b960a8d03705d1ace08b1a19da3fdcc99ddbd',
                'block_height': 2,
                'header_bytes': binascii.unhexlify(

                    '010000004860eb18bf1b1620e37e9490fc8a427514416fd75159ab86688e9a8300000000d5fdc'
                    'c541e25de1c7a5addedf24858b8bb665c9f36ef744ee42c316022c90f9bb0bc6649ffff001d08d2bd61'
                ),
                'prev_block_hash': '00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048'
            },
            {
                'block_hash': '0000000082b5015589a3fdf2d4baff403e6f0be035a5d9742c1cae6295464449',
                'block_height': 3,
                'header_bytes': binascii.unhexlify(

                    '01000000bddd99ccfda39da1b108ce1a5d70038d0a967bacb68b6b63065f626a0000000044f67222'
                    '6090d85db9a9f2fbfe5f0f9609b387af7be5b7fbb7a1767c831c9e995dbe6649ffff001d05e0ed6d'
                ),
                'prev_block_hash': '000000006a625f06636b8bb6ac7b960a8d03705d1ace08b1a19da3fdcc99ddbd'
            },
            {
                'block_hash': '000000004ebadb55ee9096c9a2f8880e09da59c0d68b1c228da88e48844a1485',
                'block_height': 4,
                'header_bytes': binascii.unhexlify(

                    '010000004944469562ae1c2c74d9a535e00b6f3e40ffbad4f2fda3895501b582000000007a06ea98'
                    'cd40ba2e3288262b28638cec5337c1456aaf5eedc8e9e5a20f062bdf8cc16649ffff001d2bfee0a9'
                ),
                'prev_block_hash': '0000000082b5015589a3fdf2d4baff403e6f0be035a5d9742c1cae6295464449'
            },
        ]
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

        headers2 = [
            {
                'block_hash': '000000009b7262315dbf071787ad3656097b892abffd1f95a1a022f896f533fc',
                'block_height': 5,
                'header_bytes': binascii.unhexlify(
                    '0100000085144a84488ea88d221c8bd6c059da090e88f8a2c99690ee55dbba4e00000000e11c4'
                    '8fecdd9e72510ca84f023370c9a38bf91ac5cae88019bee94d24528526344c36649ffff001d1d03e477'
                                            ),
                'prev_block_hash': '000000004ebadb55ee9096c9a2f8880e09da59c0d68b1c228da88e48844a1485'
            },
            {
                'block_hash': '000000003031a0e73735690c5a1ff2a4be82553b2a12b776fbd3a215dc8f778d',
                'block_height': 6,
                'header_bytes': binascii.unhexlify(
                    '01000000fc33f596f822a0a1951ffdbf2a897b095636ad871707bf5d3162729b00000000379dfb96a5ea8c81700ea4'
                    'ac6b97ae9a9312b2d4301a29580e924ee6761a2520adc46649ffff001d189c4c97'
                ),
                'prev_block_hash': '000000009b7262315dbf071787ad3656097b892abffd1f95a1a022f896f533fc'
            },
            {
                'block_hash': '0000000071966c2b1d065fd446b1e485b2c9d9594acd2007ccbd5441cfc89444',
                'block_height': 7,
                'header_bytes': binascii.unhexlify(
                    '010000008d778fdc15a2d3fb76b7122a3b5582bea4f21f5a0c693537e7a03130000000003f674005103b42f984169c7'
                    'd008370967e91920a6a5d64fd51282f75bc73a68af1c66649ffff001d39a59c86'
                ),
                'prev_block_hash': '000000003031a0e73735690c5a1ff2a4be82553b2a12b776fbd3a215dc8f778d'
            },
            {
                'block_hash': '00000000408c48f847aa786c2268fc3e6ec2af68e8468a34a28c61b7f1de0dc6',
                'block_height': 8,
                'header_bytes': binascii.unhexlify(
                    '010000004494c8cf4154bdcc0720cd4a59d9c9b285e4b146d45f061d2b6c967100000000e3855ed886605b6d4a99d5f'
                    'a2ef2e9b0b164e63df3c4136bebf2d0dac0f1f7a667c86649ffff001d1c4b5666'
                ),
                'prev_block_hash': '0000000071966c2b1d065fd446b1e485b2c9d9594acd2007ccbd5441cfc89444'
            },
            {
                'block_hash': '000000008d9dc510f23c2657fc4f67bea30078cc05a90eb89e84cc475c080805',
                'block_height': 9,
                'header_bytes': binascii.unhexlify(
                    '01000000c60ddef1b7618ca2348a46e868afc26e3efc68226c78aa47f8488c4000000000c997a5e56e104102fa209c'
                    '6a852dd90660a20b2d9c352423edce25857fcd37047fca6649ffff001d28404f53'
                ),
                'prev_block_hash': '00000000408c48f847aa786c2268fc3e6ec2af68e8468a34a28c61b7f1de0dc6'
            },
        ]

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
        res = self.sut.save_header(
            '000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f',
            0,
            binascii.unhexlify(
            '0100000000000000000000000000000000000000000000000000000000000000000000003ba3edfd7a7b1'
            '2b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a29ab5f49ffff001d1dac2b7c'
            ),
            None
        )
        expres = {
            'header_bytes': binascii.unhexlify(
            '0100000000000000000000000000000000000000000000000000000000000000000000003ba3ed'
            'fd7a7b12b27ac72c3e67768f617fc81bc3888a51323a9fb8aa4b1e5e4a29ab5f49ffff001d1dac2b7c'
        ),
            'block_height': 0,
            'block_hash': '000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f'}
        self.assertEqual(res, expres)
        with self.assertRaises(exceptions.HeadersInconsistencyException):
            self.sut.save_header(
                "0000000099c744455f58e6c6e98b671e1bf7f37346bfd4cf5d0274ad8ee660cb",
                1,
                binascii.unhexlify(
                "01000000a7c3299ed2475e1d6ea5ed18d5bfe243224add249cce99c5c67cc9fb00000000601c73862a0a7238e376f"
                "497783c8ecca2cf61a4f002ec8898024230787f399cb575d949ffff001d3a5de07f"),
                "0000000099c744455f58e6c6e98b671e1bf7f37346bfd4cf5d0274ad8ee660cb"
            )
