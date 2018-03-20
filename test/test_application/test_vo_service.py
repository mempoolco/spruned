import asyncio
import unittest
from unittest.mock import Mock, create_autospec
import binascii
from spruned.application.cache import CacheFileInterface
from spruned.application.spruned_vo_service import SprunedVOService
from spruned.services.thirdparty_service import ThirdPartyServiceDelegate
from test.utils import async_coro


class TestVOService(unittest.TestCase):
    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.electrod = Mock()
        self.p2p = Mock()
        self.cache = create_autospec(CacheFileInterface)
        self.utxo_tracker = Mock()
        self.repository = Mock()
        self.source = create_autospec(ThirdPartyServiceDelegate)
        self.sut = SprunedVOService(
            self.electrod, self.p2p, utxo_tracker=self.utxo_tracker, repository=self.repository
        )
        self.sut.add_cache(self.cache)
        self.sut.add_source(self.source)
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
                'bits': 391481763,
                'chainwork': 'Not Implemented Yet',
                'confirmations': 2,
                'difficulty': 'Not Implemented Yet',
                'hash': '000000000000000000376267d342878f869cb68192ff5d73f5f1953ae83e3e1e',
                'height': 513979,
                'mediantime': 1521312803,
                'merkleroot': '23d4c463811650d9860b4c191d416a11aca4d3047847f96a828d4d576a3a0448',
                'nextblockhash': None,
                'nonce': 2500253276,
                'previousblockhash': '0000000000000000004c3270bc11b00779e2a9ce2cdbc67a26a339abec01d06a',
                'time': 1521312803,
                'version': 536870912,
                'versionHex': 'Not Implemented Yet'
            }

    def tearDown(self):
        self.electrod.reset_mock()
        self.cache.reset_mock()
        self.utxo_tracker.reset_mock()
        self.repository.reset_mock()

    def test_getblock_non_verbose(self):
        self.cache.get.return_value = None
        self.repository.get_best_header.return_value = {'block_height': 513980}
        self.repository.get_block_header.return_value = self.header
        self.repository.get_block.return_value = {
                'block_hash': '000000000000000000376267d342878f869cb68192ff5d73f5f1953ae83e3e1e',
                'block_bytes': binascii.unhexlify('cafebabe'.encode())
            }

        block = self.loop.run_until_complete(
            self.sut.getblock('000000000000000000376267d342878f869cb68192ff5d73f5f1953ae83e3e1e', 0)
        )
        self.assertEqual(block, 'cafebabe')

    def test_getrawtransaction(self):
        self.cache.get.return_value = None
        self.repository.get_block_header.return_value = self.header
        tx = '01000000000101531213685738c91df5ceb1537605b4e17d0e623c34ead12b9e285495cd5da9b80000000000ffffffff0248d' \
             '00500000000001976a914fa511ca56ee17f57b8190ad490c4e5bf7ef0e34b88ac951e00000000000016001458e05b9b412c3b' \
             '4f35bdb54f47376beaeb8f81aa024830450221008a6edb6ce73676d4065ffb810f3945b3c3554025d3d7545bfca7185aaff62' \
             '0cc022066e2f0640aeb0775e4b47701472b28d1018b4ab8fd688acbdcd757b75c2731b6012103dfc2e6847645ca8057120780' \
             'e5ae6fa84be76b39465cd2a5158d1fffba78b22600000000'
        self.repository.get_best_header.return_value = {'block_height': 513980}
        self.electrod.getrawtransaction.return_value = async_coro(tx)
        self.source.getrawtransaction.return_value = async_coro({
            'blockhash': '000000000000000000376267d342878f869cb68192ff5d73f5f1953ae83e3e1e',
            'source': 'some unreliable api'
        })
        self.electrod.getmerkleproof.return_value = async_coro(True)
        res = self.loop.run_until_complete(
            self.sut.getrawtransaction(
                'dbae729fc6cce1bc922e66f4f12eb2b43ef57406bf5a0818eb2e73696b713b91',
                verbose=False
            )
        )
        self.assertEqual(res, tx)

    def test_getbestblockhash(self):
        self.repository.get_best_header.return_value = {'block_hash': 'cafebabe'}
        res = self.loop.run_until_complete(self.sut.getbestblockhash())
        self.assertEqual(res, 'cafebabe')

    def test_getblockhash(self):
        self.repository.get_block_hash.return_value = 'cafebabe'
        res = self.loop.run_until_complete(self.sut.getblockhash(123))
        self.assertEqual(res, 'cafebabe')

    def test_getblockheader(self):
        self.repository.get_best_header.return_value = {'block_height': 513980}
        self.repository.get_block_header.return_value = self.header
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
        self.repository.get_best_header.return_value = {'block_height': 6}
        res = self.loop.run_until_complete(self.sut.getblockcount())
        self.assertEqual(res, 6)

    def test_estimatefee(self):
        self.electrod.estimatefee.return_value = async_coro('fee estimation')
        res = self.loop.run_until_complete(self.sut.estimatefee(6))
        self.assertEqual(res, 'fee estimation')

    def test_getbestblockheader(self):
        self.repository.get_best_header.return_value = {
            'block_height': 513980,
            'block_hash': '0000000000000000001a0822fbaef92ef048967fa32c68f96e3d57d13183ef2b'
        }
        self.repository.get_block_header.return_value = self.header
        res = self.loop.run_until_complete(self.sut.getbestblockheader(verbose=False))
        self.assertEqual(
            res,
            '000000206ad001ecab39a3267ac6db2ccea9e27907b011bc70324c00000000000000000048043a6a'
            '574d8d826af9477804d3a4ac116a411d194c0b86d950168163c4d4232364ad5aa38955175cd60695'
        )

        res = self.loop.run_until_complete(self.sut.getbestblockheader(verbose=True))
        self.assertEqual(res, self.response_header)

    def test_getblockchaininfo(self):
        self.repository.get_best_header.return_value = self.header
        res = self.loop.run_until_complete(self.sut.getblockchaininfo())
        self.assertEqual(
            res,
            {
                'chain': 'main',
                'warning': 'spruned v0.0.1. emulating bitcoind v0.16',
                'blocks': 513979,
                'headers': 513979,
                'bestblockhash': '000000000000000000376267d342878f869cb68192ff5d73f5f1953ae83e3e1e',
                'difficulty': None,
                'chainwork': None,
                'mediantime': 1521312803,
                'verificationprogress': 0,
                'pruned': False
             }
        )

    def test_gettxout_ok(self):
        TXID = 'aa'*32
        INDEX = 0
        self.source.gettxout.return_value = async_coro(
            {
                'in_block': 123,
                'value_satoshi': 10000,
                'script_asm': 'asm',
                'script_hex': '61736d',
                'script_type': 'script_type',
                'addresses': ['1btc'],
                'unspent': True
            }
        )
        self.electrod.listunspents.return_value = async_coro([
            {'tx_hash': TXID, 'tx_pos': INDEX}
        ])