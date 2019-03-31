import asyncio
from unittest import TestCase
from unittest.mock import Mock

from spruned.daemon.electrod.electrod_fee_estimation import EstimateFeeConsensusProjector, EstimateFeeConsensusCollector
from spruned.daemon.electrod.electrod_interface import ElectrodInterface
from test.utils import async_coro


class TestFeeEstimation(TestCase):
    def setUp(self):
        self.pool = Mock()
        self.fees_projector = EstimateFeeConsensusProjector()
        self.fees_collector = EstimateFeeConsensusCollector()
        self.fees_collector.add_permanent_connections_pool(self.pool)
        self.sut = ElectrodInterface(self.pool, fees_collector=self.fees_collector, fees_projector=self.fees_projector)
        self.loop = asyncio.get_event_loop()

    def load_fee_response(self, target):
        m = Mock()
        m.RPC.side_effect = lambda x, y: async_coro(target)
        return m

    def test_estimatefee_1(self):
        disagree = Mock(hostname='peer3', client=self.load_fee_response(0.00005))
        self.pool.established_connections = [
            Mock(hostname='peer1', client=self.load_fee_response(0.00003)),
            Mock(hostname='peer2', client=self.load_fee_response(0.00003)),
            disagree
        ]
        self.pool.get_peer_for_hostname.return_value = disagree
        x = self.loop.run_until_complete(self.sut.estimatefee(6))
        int(x.pop('timestamp'))
        points = x.pop('points')
        points.remove(5)
        points.remove(3)
        points.remove(3)
        self.assertEqual(
            x,
            {
                'agree': True,
                'agreement': 66,
                'average': 3,
                'average_satoshi_per_kb': 0.00003,
                'disagree': ['peer3'],
                'median': 3,
            }
        )
        Mock.assert_called_with(disagree.disconnect)
