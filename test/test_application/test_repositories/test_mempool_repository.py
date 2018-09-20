from unittest import TestCase
import os
import time
from unittest.mock import Mock, ANY

from spruned.repositories.mempool_repository import MempoolRepository


class TestMempoolRepository(TestCase):
    def setUp(self):
        self.sut = MempoolRepository()
        self._test_timestamp = int(time.time())

    def tearDown(self):
        pass

    def _get_transaction(self, txid, size, outpoints):
        return {
            "outpoints": outpoints,
            "bytes": os.urandom(size),
            "size": size,
            "txid": txid,
            "timestamp": self._test_timestamp
        }

    def test_mempool_with_failed_double_spend(self):
        """
        we see the double spend, the miners too
        """
        transaction1 = self._get_transaction('txid1', 100, ['cafe:1', 'babe:1'])
        transaction2 = self._get_transaction('txid2', 100, ['cafe:2', 'babe:2'])

        double_spend_1 = self._get_transaction('txid3', 100, ['cafe:1'])
        if self.sut.add_seen('txid1', 'test'):
            self.sut.add_transaction('txid1', transaction1)
        if self.sut.add_seen('txid2', 'test'):
            self.sut.add_transaction('txid2', transaction2)
        self.sut.add_seen('txid3', 'test')

        raw_mempool_1 = self.sut.get_mempool_info()

        self.sut.add_transaction('txid3', double_spend_1)

        raw_mempool_2 = self.sut.get_mempool_info()

        self.assertEqual(raw_mempool_1, raw_mempool_2)
        self.assertEqual(list(self.sut._double_spends_by_outpoint.keys()), ['cafe:1'])
        self.assertEqual(self.sut._double_spends_by_outpoint['cafe:1'], {'txid3'})

        double_spends = self.sut._double_spends
        for double_spend in double_spends.values():
            double_spend.pop('bytes')

        self.assertEqual(
            double_spends,
            {
                'txid3': {
                    'outpoints': ['cafe:1'], 'size': 100, 'txid': 'txid3', 'timestamp': self._test_timestamp
                }
            }
        )
        tx1 = Mock()
        tx1.w_hash.return_value = 'txid1'
        tx2 = Mock()
        tx2.w_hash.return_value = 'txid2'
        block = Mock(txs=[tx1, tx2])
        self.sut.on_new_block(block)
        self.assertEqual(self.sut.get_mempool_info(), {'size': 0, 'bytes': 0, 'maxmempool': 50000, 'last_update': ANY})
        self.assertEqual(self.sut._double_spends, {})
        self.assertEqual(self.sut._double_spends_by_outpoint, {})
        self.assertEqual(self.sut._transactions, {})

    def test_mempool_with_successful_double_spend(self):
        """
        we see the double spend, the miners don't
        """
        transaction1 = self._get_transaction('txid1', 100, ['cafe:1', 'babe:1'])
        transaction2 = self._get_transaction('txid2', 100, ['cafe:2', 'babe:2'])

        double_spend_1 = self._get_transaction('txid3', 100, ['cafe:1'])

        self.sut.add_seen('txid1', 'test')
        self.sut.add_seen('txid2', 'test')
        self.sut.add_seen('txid3', 'test')

        self.sut.add_transaction('txid1', transaction1)
        self.sut.add_transaction('txid2', transaction2)

        raw_mempool_1 = self.sut.get_mempool_info()

        self.sut.add_transaction('txid3', double_spend_1)

        raw_mempool_2 = self.sut.get_mempool_info()

        self.assertEqual(raw_mempool_1, raw_mempool_2)
        self.assertEqual(list(self.sut._double_spends_by_outpoint.keys()), ['cafe:1'])
        self.assertEqual(self.sut._double_spends_by_outpoint['cafe:1'], {'txid3'})

        double_spends = self.sut._double_spends
        for double_spend in double_spends.values():
            double_spend.pop('bytes')

        self.assertEqual(
            double_spends,
            {
                'txid3': {
                    'outpoints': ['cafe:1'], 'size': 100, 'txid': 'txid3', 'timestamp': self._test_timestamp
                }
            }
        )
        tx2 = Mock()
        tx2.w_hash.return_value = 'txid2'
        tx3 = Mock()
        tx3.w_hash.return_value = 'txid3'
        block = Mock(txs=[tx2, tx3])
        self.sut.on_new_block(block)

        self.assertEqual(self.sut._double_spends, {})
        self.assertEqual(self.sut._double_spends_by_outpoint, {})
        self.assertEqual(self.sut._transactions, {})
        self.assertEqual(self.sut.get_mempool_info(), {'size': 0, 'bytes': 0, 'maxmempool': 50000, 'last_update': ANY})
