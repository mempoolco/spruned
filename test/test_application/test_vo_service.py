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
from spruned.daemon.exceptions import ElectrumMissingResponseException
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
            'chainwork': '00' * 32,
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
            'chainwork': '00' * 32,
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
            'chainwork': '00' * 32,
            "previousblockhash": "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
            "nextblockhash": "000000006a625f06636b8bb6ac7b960a8d03705d1ace08b1a19da3fdcc99ddbd",
            "tx": [
                "0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098"
            ],
            "confirmations": 513980
        }
        self.assertEqual(block, block_json)

    def test_getblock_non_verbose(self):
        self.repository.headers.get_best_header.return_value = {'block_height': 1513040}
        self.repository.headers.get_block_header.return_value = {
            'header_bytes': binascii.unhexlify(
                '00000020ee17da57f0b06ea0a8af02ca37f35fca5e4f2019ce14c11ed5000000000000006ee871a4'
                'e8048a8c50cb454a142a646509e91b7b94aa615ad4df88922323dbb5b079c55c28f7031abe98b88e'
            ),
            'block_height': 1513040,
            'block_hash': '0000000000000338dac26bdf4d7bffd4f1b579307fd00b084a6b477c4d568e87'
        }
        res = [
            {
                'transaction_bytes': binascii.unhexlify(
                    '020000000001010000000000000000000000000000000000000000000000000000000000000000ffffffff1f035016'
                    '1704a979c55c50616e64614d696e6572010000008f09000000000000ffffffff02303d5402000000001976a914f6db'
                    'b4bc1980e00aa667095f4627e329ed8b58e888ac0000000000000000266a24aa21a9ed158b2c49cf4ce2dc1cc96855'
                    '7a22252907e5c036c7e26e598c54d3f003bb072a012000000000000000000000000000000000000000000000000000'
                    '0000000000000000000000'
                )
            },
            {
                'transaction_bytes': binascii.unhexlify(
                    '0100000004a4459971d9b54fe5bd2fc45c65bf1e8355078deb7ddef3a6cf74d69aeebf39ce01000000fc004730440'
                    '2201a5714841e19753811657e00d1db0d90fd47a784bfedecfbd8661a3b82f27f2f0220744f3b6f6b6d0ae5bd337e'
                    '6b32bca7944bf9c763d072ac9951984aa1710df4510147304402203f1d05dd0a14f4e5855a6c28e97bd60102fb405'
                    'd839a09790de1582eb7a7c6ad02201e05a745c3c57b6fc84032b761f7c57e03461194d3c65e62b9dc1481bf7c5e9f'
                    '014c6952210343e12e54cadfa2b908338c0c3bb15934c977069bb87abea5a45dd7e539c1efad2102be82fd3f24b0a'
                    '5b82f5046075fca1a14c9917815cf095949a2249c9cd2dde45f21037d6f48f518610e6ff1b88b6354b199837e734a'
                    '02ffdff8cd2bd81042fa682f2153aeffffffffa4459971d9b54fe5bd2fc45c65bf1e8355078deb7ddef3a6cf74d69'
                    'aeebf39ce00000000fdfe0000483045022100ce59ba9f8b79488826bc7bf7f64d7cfdd46703957286bf06794feef7'
                    'e220b7010220479b09020ef3c074e0e50a64d999b328e4f04cc73f870a63e2e3ba12d06d8ed601483045022100b17'
                    '3060a26f9407a05be951fdf9001e66772fbbe1c2cabcdc1e9718e113ef754022071f13e024502ef63e38163604bb8'
                    'd32c9f56bad5c380479f521364e394a425bc014c6952210343e12e54cadfa2b908338c0c3bb15934c977069bb87ab'
                    'ea5a45dd7e539c1efad2102be82fd3f24b0a5b82f5046075fca1a14c9917815cf095949a2249c9cd2dde45f21037d'
                    '6f48f518610e6ff1b88b6354b199837e734a02ffdff8cd2bd81042fa682f2153aeffffffffa4459971d9b54fe5bd2'
                    'fc45c65bf1e8355078deb7ddef3a6cf74d69aeebf39ce06000000fc004730440220482f9f39f1dc5bed57eb8514da'
                    'c0ebdd6edcd9e7ba00efb17c32f2bc3f6ac8dd02207d968e7ce2afdeffd7ee6026f610b886da2612de8c1186521c8'
                    '0f220f766c8180147304402207cd05a63ef5c98eb06bf5e36aefc589a414340b8ba77f04d0d28c33a622ab9380220'
                    '617104c98101e0669d907540c2ba8bd04212f0741f9c1826bb3d807307c37bdf014c6952210343e12e54cadfa2b90'
                    '8338c0c3bb15934c977069bb87abea5a45dd7e539c1efad2102be82fd3f24b0a5b82f5046075fca1a14c9917815cf'
                    '095949a2249c9cd2dde45f21037d6f48f518610e6ff1b88b6354b199837e734a02ffdff8cd2bd81042fa682f2153a'
                    'effffffff2668f67d4fdcfc602d3a093fc337a964902df6fd8074ceac7dd91c2ea056044e00000000fdfe00004830'
                    '450221008689d4269fd9fb62c3c162c0cca86b7f5c0c47a2b24bc25f25b19d8c173df8c50220435a04d3cf53c0765'
                    '85b4e35ec400adc8b4b1a860fc698c9bf79e8ba510004f4014830450221009f3ccc876a119e93d7ff5398ffa089d1'
                    '5677ef5a81683b42f5ab492e2b19d9a3022063e39ff620ff002e8ee6e110d64227cc3b925dba5a1e0ee515de17b7f'
                    '3430b88014c69522102ed5f3b5a66a87b3c5808a94776966cac7f386dc03e7d3059cf53dc529a87567221033b3b6f'
                    'c2ab5aedc5e86faafff27a488afd14bfd79a4bed9e94a0b2b2e7b5d7ca2102ca331b1b83826ccd634df17de075d4b'
                    'a275034bccd56db2a7cba42f8f6d1d00653aeffffffff02177d07000000000017a9147616351f016c02c5f565262e'
                    '271a82c178fa710987d77b07000000000017a914e8a4fea3a59687bef29a55a0566ce3945fa833bd874f161700'
                )
            }
        ]
        self.repository.blockchain.get_transactions_by_block_hash.return_value = res, 16

        block = self.loop.run_until_complete(
            self.sut.getblock('0000000000000338dac26bdf4d7bffd4f1b579307fd00b084a6b477c4d568e87', 0)
        )
        self.assertEqual(
            block,
            '00000020ee17da57f0b06ea0a8af02ca37f35fca5e4f2019ce14c11ed5000000000000006ee871a4e8048a8c50cb454a14'
            '2a646509e91b7b94aa615ad4df88922323dbb5b079c55c28f7031abe98b88e020200000000010100000000000000000000'
            '00000000000000000000000000000000000000000000ffffffff1f0350161704a979c55c50616e64614d696e6572010000'
            '008f09000000000000ffffffff02303d5402000000001976a914f6dbb4bc1980e00aa667095f4627e329ed8b58e888ac00'
            '00000000000000266a24aa21a9ed158b2c49cf4ce2dc1cc968557a22252907e5c036c7e26e598c54d3f003bb072a012000'
            '00000000000000000000000000000000000000000000000000000000000000000000000100000004a4459971d9b54fe5bd'
            '2fc45c65bf1e8355078deb7ddef3a6cf74d69aeebf39ce01000000fc0047304402201a5714841e19753811657e00d1db0d'
            '90fd47a784bfedecfbd8661a3b82f27f2f0220744f3b6f6b6d0ae5bd337e6b32bca7944bf9c763d072ac9951984aa1710d'
            'f4510147304402203f1d05dd0a14f4e5855a6c28e97bd60102fb405d839a09790de1582eb7a7c6ad02201e05a745c3c57b'
            '6fc84032b761f7c57e03461194d3c65e62b9dc1481bf7c5e9f014c6952210343e12e54cadfa2b908338c0c3bb15934c977'
            '069bb87abea5a45dd7e539c1efad2102be82fd3f24b0a5b82f5046075fca1a14c9917815cf095949a2249c9cd2dde45f21'
            '037d6f48f518610e6ff1b88b6354b199837e734a02ffdff8cd2bd81042fa682f2153aeffffffffa4459971d9b54fe5bd2f'
            'c45c65bf1e8355078deb7ddef3a6cf74d69aeebf39ce00000000fdfe0000483045022100ce59ba9f8b79488826bc7bf7f6'
            '4d7cfdd46703957286bf06794feef7e220b7010220479b09020ef3c074e0e50a64d999b328e4f04cc73f870a63e2e3ba12'
            'd06d8ed601483045022100b173060a26f9407a05be951fdf9001e66772fbbe1c2cabcdc1e9718e113ef754022071f13e02'
            '4502ef63e38163604bb8d32c9f56bad5c380479f521364e394a425bc014c6952210343e12e54cadfa2b908338c0c3bb159'
            '34c977069bb87abea5a45dd7e539c1efad2102be82fd3f24b0a5b82f5046075fca1a14c9917815cf095949a2249c9cd2dd'
            'e45f21037d6f48f518610e6ff1b88b6354b199837e734a02ffdff8cd2bd81042fa682f2153aeffffffffa4459971d9b54f'
            'e5bd2fc45c65bf1e8355078deb7ddef3a6cf74d69aeebf39ce06000000fc004730440220482f9f39f1dc5bed57eb8514da'
            'c0ebdd6edcd9e7ba00efb17c32f2bc3f6ac8dd02207d968e7ce2afdeffd7ee6026f610b886da2612de8c1186521c80f220'
            'f766c8180147304402207cd05a63ef5c98eb06bf5e36aefc589a414340b8ba77f04d0d28c33a622ab9380220617104c981'
            '01e0669d907540c2ba8bd04212f0741f9c1826bb3d807307c37bdf014c6952210343e12e54cadfa2b908338c0c3bb15934'
            'c977069bb87abea5a45dd7e539c1efad2102be82fd3f24b0a5b82f5046075fca1a14c9917815cf095949a2249c9cd2dde4'
            '5f21037d6f48f518610e6ff1b88b6354b199837e734a02ffdff8cd2bd81042fa682f2153aeffffffff2668f67d4fdcfc60'
            '2d3a093fc337a964902df6fd8074ceac7dd91c2ea056044e00000000fdfe00004830450221008689d4269fd9fb62c3c162'
            'c0cca86b7f5c0c47a2b24bc25f25b19d8c173df8c50220435a04d3cf53c076585b4e35ec400adc8b4b1a860fc698c9bf79'
            'e8ba510004f4014830450221009f3ccc876a119e93d7ff5398ffa089d15677ef5a81683b42f5ab492e2b19d9a3022063e3'
            '9ff620ff002e8ee6e110d64227cc3b925dba5a1e0ee515de17b7f3430b88014c69522102ed5f3b5a66a87b3c5808a94776'
            '966cac7f386dc03e7d3059cf53dc529a87567221033b3b6fc2ab5aedc5e86faafff27a488afd14bfd79a4bed9e94a0b2b2'
            'e7b5d7ca2102ca331b1b83826ccd634df17de075d4ba275034bccd56db2a7cba42f8f6d1d00653aeffffffff02177d0700'
            '0000000017a9147616351f016c02c5f565262e271a82c178fa710987d77b07000000000017a914e8a4fea3a59687bef29a'
            '55a0566ce3945fa833bd874f161700'
        )

    def test_getblock_p2p_non_verbose(self):
        hex_block = '010000006fe28c0ab6f1b372c1a6a246ae63f74f931e8365e15a089c68d6190000000000982051fd1e4ba744bbbe6' \
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
            'chainwork': '00' * 32,
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
            'chainwork': '00' * 32,
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
        self.electrod.get_merkleproof.return_value = async_coro({'block_height': 1, 'merkle': ['ff' * 32], 'pos': 0})
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
        self.electrod.estimatefee.side_effect = [ElectrumMissingResponseException(), async_coro(3)]
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
                'chainwork': '00' * 32,
                'mediantime': 1521312803,
                'verificationprogress': 0,
                'pruned': False,
                'initialblockdownload': False
            }
        )

    def test_gettxout(self):
        tx = '01000000010000000000000000000000000000000000000000000000000000000000000000ffffffff0704ffff00' \
             '1d0104ffffffff0100f2052a0100000043410496b538e853519c726a2c91e61ec11600ae1390813a627c66fb8be7' \
             '947be63c52da7589379515d4e0a604f8141781e62294721166bf621e73a82cbf2342c858eeac00000000'
        self.repository.get_best_header.return_value = {'block_height': 513980}
        self.electrod.getrawtransaction.return_value = async_coro(tx)
        self.repository.blockchain.get_transaction.return_value = None
        self.electrod.listunspents_by_scripthash.side_effect = [ElectrumMissingResponseException,
                                                                async_coro(
                                                                    [{
                                                                         'tx_hash': '0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098',
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
