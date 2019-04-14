
import asyncio
import io
import json
import unittest
from unittest.mock import Mock, create_autospec
import binascii

from pycoin.block import Block

from spruned import settings

from spruned.application.cache import CacheAgent
from spruned.application.exceptions import ServiceException, InvalidPOWException
from spruned.application.spruned_vo_service import SprunedVOService
from spruned.daemon.exceptions import ElectrodMissingResponseException
from test.utils import async_coro


class TestVOService(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.electrod = Mock()
        self.p2p = Mock()
        self.repository = Mock()
        self.cache = create_autospec(CacheAgent)
        self.sut = SprunedVOService(
            self.electrod, self.p2p, cache_agent=self.cache, repository=self.repository
        )
        hb = '000000206ad001ecab39a3267ac6db2ccea9e27907b011bc70324c00000000000000000048043a6a' \
             '574d8d826af9477804d3a4ac116a411d194c0b86d950168163c4d4232364ad5aa38955175cd60695'
        hh = '000000000000000000376267d342878f869cb68192ff5d73f5f1953ae83e3e1e'
        hb = binascii.unhexlify(hb.encode())
        self.header = {
            'header_bytes': hb,
            'block_hash': hh,
            'block_height': 513979,
            'prev_block_hash': '0000000000000000004c3270bc11b00779e2a9ce2cdbc67a26a339abec01d06a'
        }
        self.response_header = {
                'bits': '391481763',
                'chainwork': '00'*32,
                'confirmations': 2,
                'difficulty': 0,
                'hash': '000000000000000000376267d342878f869cb68192ff5d73f5f1953ae83e3e1e',
                'height': 513979,
                'mediantime': 1521312803,
                'merkleroot': '23d4c463811650d9860b4c191d416a11aca4d3047847f96a828d4d576a3a0448',
                'nextblockhash': None,
                'nonce': 2500253276,
                'previousblockhash': '0000000000000000004c3270bc11b00779e2a9ce2cdbc67a26a339abec01d06a',
                'time': 1521312803,
                'version': 536870912,
                'versionHex': ''
            }

    def tearDown(self):
        self.electrod.reset_mock()
        self.repository.reset_mock()

    def test_getblock_not_found(self):
        self.repository.headers.get_block_header.return_value = None
        block = self.loop.run_until_complete(
            self.sut.getblock('00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048', 1)
        )
        self.assertEqual(block, None)

    def test_getblock_full_verbose(self):
        self.repository.headers.get_block_header.return_value = None
        with self.assertRaises(NotImplementedError):
            self.loop.run_until_complete(
                self.sut.getblock('00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048', 2)
            )

    def test_getblock_verbose(self):
        header_hex = '010000006fe28c0ab6f1b372c1a6a246ae63f74f931e8365e15a089c68d6190000000000982051' \
                     'fd1e4ba744bbbe680e1fee14677ba1a3c3540bf7b1cdb606e857233e0e61bc6649ffff001d01e36299'
        block_json = {
              "hash": "00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048",
              "height": 1,
              "version": 1,
              "versionHex": "",
              "merkleroot": "0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098",
              "time": 1231469665,
              "mediantime": 1231469665,
              "nonce": 2573394689,
              "bits": 486604799,
              "difficulty": 0,
              'chainwork': '00'*32,
              "previousblockhash": "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
              "nextblockhash": "000000006a625f06636b8bb6ac7b960a8d03705d1ace08b1a19da3fdcc99ddbd",
              "tx": [
                "0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098"
              ]
        }
        self.repository.headers.get_best_header.return_value = {'block_height': 513980}
        self.repository.headers.get_block_header.return_value = {
            'block_hash': block_json['hash'],
            'block_height': block_json['height'],
            'header_bytes': binascii.unhexlify(header_hex.encode()),
            'next_block_hash': block_json['nextblockhash']
        }
        self.repository.blockchain.get_txids_by_block_hash.return_value = [
            '0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098'
        ], 215

        block = self.loop.run_until_complete(
            self.sut.getblock('00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048', 1)
        )
        block_json = {
              "hash": "00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048",
              "height": 1,
              "size": 215,
              "version": 1,
              "versionHex": "",
              "merkleroot": "0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098",
              "time": 1231469665,
              "mediantime": 1231469665,
              "nonce": 2573394689,
              "bits": '486604799',
              "difficulty": 0,
              'chainwork': '00'*32,
              "previousblockhash": "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
              "nextblockhash": "000000006a625f06636b8bb6ac7b960a8d03705d1ace08b1a19da3fdcc99ddbd",
              "tx": [
                "0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098"
              ],
              "confirmations": 513980
        }
        self.assertEqual(block, block_json)

    def test_getblock_non_verbose(self):
        self.repository.headers.get_best_header.return_value = {'block_height': 513980}
        self.repository.headers.get_block_header.return_value = self.header
        self.repository.blockchain.get_transactions_by_block_hash\
            .return_value = [{'transaction_bytes': b'cafebabe'*4}], 16

        block = self.loop.run_until_complete(
            self.sut.getblock('000000000000000000376267d342878f869cb68192ff5d73f5f1953ae83e3e1e', 0)
        )
        self.assertEqual(
            block, '000000206ad001ecab39a3267ac6db2ccea9e27907b011bc70324c00000000000000000048043a6a574d8d826af'
                   '9477804d3a4ac116a411d194c0b86d950168163c4d4232364ad5aa38955175cd606956361666562616265636166'
                   '656261626563616665626162656361666562616265'
        )

    def test_getblock_p2p_non_verbose(self):
        hex_block ='010000006fe28c0ab6f1b372c1a6a246ae63f74f931e8365e15a089c68d6190000000000982051fd1e4ba744bbbe6' \
                   '80e1fee14677ba1a3c3540bf7b1cdb606e857233e0e61bc6649ffff001d01e3629901010000000100000000000000' \
                   '00000000000000000000000000000000000000000000000000ffffffff0704ffff001d0104ffffffff0100f2052a0' \
                   '100000043410496b538e853519c726a2c91e61ec11600ae1390813a627c66fb8be7947be63c52da7589379515d4e0' \
                   'a604f8141781e62294721166bf621e73a82cbf2342c858eeac00000000'
        bytes_block = binascii.unhexlify(hex_block.encode())

        self.repository.headers.get_best_header.return_value = {'block_height': 513980}
        self.repository.headers.get_block_header.return_value = self.header
        self.repository.blockchain.get_transactions_by_block_hash.return_value = [], None
        self.repository.blockchain.async_save_block.side_effect = [async_coro(True), async_coro(True)]
        self.p2p.get_block.side_effect = [
            async_coro(None),
            async_coro(
                {
                    'block_hash': '00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048',
                    'block_bytes': bytes_block,
                    'block_object': Block.parse(io.BytesIO(bytes_block))
                }
            )
        ]

        block = self.loop.run_until_complete(
            self.sut.getblock('000000000000000000376267d342878f869cb68192ff5d73f5f1953ae83e3e1e', 0)
        )
        self.assertEqual(block, hex_block)

    def test_getblock_p2p_non_verbose_network_error(self):
        self.repository.headers.get_best_header.return_value = {'block_height': 513980}
        self.repository.headers.get_block_header.return_value = self.header
        self.repository.blockchain.get_transactions_by_block_hash.return_value = [], None
        self.p2p.get_block.side_effect = lambda *a, **kw: async_coro(None)
        with self.assertRaises(ServiceException):
            self.loop.run_until_complete(
                self.sut.getblock('000000000000000000376267d342878f869cb68192ff5d73f5f1953ae83e3e1e', 0)
            )

    def test_getrawtransaction_non_verbose_not_in_block(self):
        tx = {
            'hex': '01000000000101531213685738c91df5ceb1537605b4e17d0e623c34ead12b9e285495cd5da9b80000000000ffffffff0248d'
                   '00500000000001976a914fa511ca56ee17f57b8190ad490c4e5bf7ef0e34b88ac951e00000000000016001458e05b9b412c3b'
                   '4f35bdb54f47376beaeb8f81aa024830450221008a6edb6ce73676d4065ffb810f3945b3c3554025d3d7545bfca7185aaff62'
                   '0cc022066e2f0640aeb0775e4b47701472b28d1018b4ab8fd688acbdcd757b75c2731b6012103dfc2e6847645ca8057120780'
                   'e5ae6fa84be76b39465cd2a5158d1fffba78b22600000000',
            'vout': []
        }
        self.electrod.getrawtransaction.return_value = async_coro(tx)
        self.repository.blockchain.get_transaction.return_value = None
        res = self.loop.run_until_complete(
            self.sut.getrawtransaction(
                'dbae729fc6cce1bc922e66f4f12eb2b43ef57406bf5a0818eb2e73696b713b91',
                verbose=False
            )
        )
        self.assertEqual(res, tx['hex'])

    def test_getrawtransaction_verbose_not_in_block(self):
        self.repository.get_block_header.return_value = self.header
        self.repository.blockchain.get_json_transaction.return_value = None
        tx = {
            'hex': '01000000000101531213685738c91df5ceb1537605b4e17d0e623c34ead12b9e285495cd5da9b80000000000ffffffff0248d'
                   '00500000000001976a914fa511ca56ee17f57b8190ad490c4e5bf7ef0e34b88ac951e00000000000016001458e05b9b412c3b'
                   '4f35bdb54f47376beaeb8f81aa024830450221008a6edb6ce73676d4065ffb810f3945b3c3554025d3d7545bfca7185aaff62'
                   '0cc022066e2f0640aeb0775e4b47701472b28d1018b4ab8fd688acbdcd757b75c2731b6012103dfc2e6847645ca8057120780'
                   'e5ae6fa84be76b39465cd2a5158d1fffba78b22600000000',
            'vout': []
        }
        self.repository.get_best_header.return_value = {'block_height': 513980}
        self.electrod.getrawtransaction.return_value = async_coro(tx)
        res = self.loop.run_until_complete(
            self.sut.getrawtransaction(
                'dbae729fc6cce1bc922e66f4f12eb2b43ef57406bf5a0818eb2e73696b713b91',
                verbose=True
            )
        )
        self.assertEqual(res, tx)

    def test_getrawtransaction_verbose_in_block(self):
        header_hex = '010000006fe28c0ab6f1b372c1a6a246ae63f74f931e8365e15a089c68d6190000000000982051' \
                     'fd1e4ba744bbbe680e1fee14677ba1a3c3540bf7b1cdb606e857233e0e61bc6649ffff001d01e36299'
        block_json = {
              "hash": "00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048",
              "height": 1,
              "version": 1,
              "versionHex": "",
              "merkleroot": "0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098",
              "time": 1231469665,
              "mediantime": 1231469665,
              "nonce": 2573394689,
              "bits": 486604799,
              "difficulty": 0,
              'chainwork': '00'*32,
              "previousblockhash": "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
              "nextblockhash": "000000006a625f06636b8bb6ac7b960a8d03705d1ace08b1a19da3fdcc99ddbd",
              "tx": [
                "0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098"
              ]
        }
        self.repository.headers.get_best_header.return_value = {'block_height': 513980}
        self.repository.headers.get_block_header.return_value = {
            'block_hash': block_json['hash'],
            'block_height': block_json['height'],
            'header_bytes': binascii.unhexlify(header_hex.encode()),
            'next_block_hash': block_json['nextblockhash']
        }
        self.repository.get_block_header.return_value = self.header
        self.repository.blockchain.get_json_transaction.return_value = None
        tx = {
            'hex': '01000000010000000000000000000000000000000000000000000000000000000000000000ffffffff0704ffff00'
                   '1d0104ffffffff0100f2052a0100000043410496b538e853519c726a2c91e61ec11600ae1390813a627c66fb8be7'
                   '947be63c52da7589379515d4e0a604f8141781e62294721166bf621e73a82cbf2342c858eeac00000000',

            'blockhash': '00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048',
            'confirmations': 6,
            'vout': []
        }
        self.repository.get_best_header.return_value = {'block_height': 513980}
        self.electrod.getrawtransaction.return_value = async_coro(tx)
        self.electrod.get_merkleproof.return_value = async_coro({'block_height': 1, 'merkle': [], 'pos': 0})
        res = self.loop.run_until_complete(
            self.sut.getrawtransaction(
                '0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098',
                verbose=True
            )
        )
        self.assertEqual(res, tx)

    def test_getrawtransaction_verbose_in_block_invalid_pow(self):
        header_hex = '010000006fe28c0ab6f1b372c1a6a246ae63f74f931e8365e15a089c68d6190000000000982051' \
                     'fd1e4ba744bbbe680e1fee14677ba1a3c3540bf7b1cdb606e857233e0e61bc6649ffff001d01e36299'
        block_json = {
            "hash": "00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048",
            "height": 1,
            "version": 1,
            "versionHex": "",
            "merkleroot": "0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098",
            "time": 1231469665,
            "mediantime": 1231469665,
            "nonce": 2573394689,
            "bits": 486604799,
            "difficulty": 0,
            'chainwork': '00'*32,
            "previousblockhash": "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
            "nextblockhash": "000000006a625f06636b8bb6ac7b960a8d03705d1ace08b1a19da3fdcc99ddbd",
            "tx": [
                "0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098"
            ]
        }
        self.repository.headers.get_best_header.return_value = {'block_height': 513980}
        self.repository.headers.get_block_header.return_value = {
            'block_hash': block_json['hash'],
            'block_height': block_json['height'],
            'header_bytes': binascii.unhexlify(header_hex.encode()),
            'next_block_hash': block_json['nextblockhash']
        }
        self.repository.get_block_header.return_value = self.header
        self.repository.blockchain.get_json_transaction.return_value = None
        tx = {
            'hex': '01000000010000000000000000000000000000000000000000000000000000000000000000ffffffff0704ffff00'
                   '1d0104ffffffff0100f2052a0100000043410496b538e853519c726a2c91e61ec11600ae1390813a627c66fb8be7'
                   '947be63c52da7589379515d4e0a604f8141781e62294721166bf621e73a82cbf2342c858eeac00000000',

            'blockhash': '00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048',
            'confirmations': 6,
            'vout': []
        }
        self.repository.get_best_header.return_value = {'block_height': 513980}
        self.electrod.getrawtransaction.return_value = async_coro(tx)
        self.electrod.get_merkleproof.return_value = async_coro({'block_height': 1, 'merkle': ['ff'*32], 'pos': 0})
        with self.assertRaises(InvalidPOWException):
            self.loop.run_until_complete(
                self.sut.getrawtransaction(
                    '0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098',
                    verbose=True
                )
            )

    def test_getbestblockhash(self):
        self.repository.headers.get_best_blockhash.return_value = 'cafebabe'
        res = self.loop.run_until_complete(self.sut.getbestblockhash())
        self.assertEqual(res, 'cafebabe')

    def test_getblockhash(self):
        self.repository.headers.get_block_hash.return_value = 'cafebabe'
        res = self.loop.run_until_complete(self.sut.getblockhash(123))
        self.assertEqual(res, 'cafebabe')

    def test_getblockheader(self):
        self.repository.headers.get_best_header.return_value = {'block_height': 513980}
        self.repository.headers.get_block_header.return_value = self.header
        res = self.loop.run_until_complete(
            self.sut.getblockheader(
                '000000000000000000376267d342878f869cb68192ff5d73f5f1953ae83e3e1e'
            )
        )
        self.assertEqual(
            res,
            self.response_header
        )

    def test_block_count(self):
        self.repository.headers.get_best_header.return_value = {'block_height': 6}
        res = self.loop.run_until_complete(self.sut.getblockcount())
        self.assertEqual(res, 6)

    def test_estimatefee(self):
        self.electrod.estimatefee.side_effect = [ElectrodMissingResponseException(), async_coro(3)]
        res = self.loop.run_until_complete(self.sut.estimatefee(6))
        self.assertEqual(res, 3)

    def test_getbestblockheader(self):
        self.repository.headers.get_best_header.return_value = {
            'block_height': 513980,
            'block_hash': '0000000000000000001a0822fbaef92ef048967fa32c68f96e3d57d13183ef2b'
        }
        self.repository.headers.get_block_header.return_value = self.header
        res = self.loop.run_until_complete(self.sut.getbestblockheader(verbose=False))
        self.assertEqual(
            res,
            '000000206ad001ecab39a3267ac6db2ccea9e27907b011bc70324c00000000000000000048043a6a'
            '574d8d826af9477804d3a4ac116a411d194c0b86d950168163c4d4232364ad5aa38955175cd60695'
        )

        res = self.loop.run_until_complete(self.sut.getbestblockheader(verbose=True))
        self.assertEqual(res, self.response_header)

    def test_getblockchaininfo(self):
        from spruned import __version__ as spruned_version
        from spruned import __bitcoind_version_emulation__ as bitcoind_version
        self.repository.headers.get_best_header.return_value = self.header
        self.p2p.bootstrap_status = 0
        res = self.loop.run_until_complete(self.sut.getblockchaininfo())
        self.assertEqual(
            res,
            {
                'chain': 'main',
                'warning': 'spruned {}, emulating bitcoind v{}'.format(spruned_version, bitcoind_version),
                'blocks': 513979,
                'headers': 513979,
                'bestblockhash': '000000000000000000376267d342878f869cb68192ff5d73f5f1953ae83e3e1e',
                'difficulty': 0,
                'chainwork': '00'*32,
                'mediantime': 1521312803,
                'verificationprogress': 0,
                'pruned': False
             }
        )

    def test_gettxout(self):
        tx = '01000000010000000000000000000000000000000000000000000000000000000000000000ffffffff0704ffff00' \
             '1d0104ffffffff0100f2052a0100000043410496b538e853519c726a2c91e61ec11600ae1390813a627c66fb8be7' \
             '947be63c52da7589379515d4e0a604f8141781e62294721166bf621e73a82cbf2342c858eeac00000000'
        self.repository.get_best_header.return_value = {'block_height': 513980}
        self.electrod.getrawtransaction.return_value = async_coro(tx)
        self.repository.blockchain.get_transaction.return_value = None
        self.electrod.listunspents_by_scripthash.side_effect = [ElectrodMissingResponseException,
                                                                async_coro(
            [{'tx_hash': '0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098',
              'tx_pos': 0, 'height': 0, 'value': 1}]
        )]
        self.repository.headers.get_best_header.return_value = {
            'block_height': 513980, 'block_hash': '0000000000000000001a0822fbaef92ef048967fa32c68f96e3d57d13183ef2b'
        }
        res = self.loop.run_until_complete(
            self.sut.gettxout(
                '0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098', 0
            )
        )
        self.assertEqual(
            res,
            {
                "bestblock": "0000000000000000001a0822fbaef92ef048967fa32c68f96e3d57d13183ef2b",
                "confirmations": 513981,
                "value": "0.00000001",
                "scriptPubKey": {
                    "asm": "",
                    "hex": "410496b538e853519c726a2c91e61ec11600ae1390813a627c66fb8be7947be63c52da7"
                           "589379515d4e0a604f8141781e62294721166bf621e73a82cbf2342c858eeac",
                    "reqSigs": 0,
                    "type": "",
                    "addresses": []
                }
            }
        )
