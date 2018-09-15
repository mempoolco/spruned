from unittest import TestCase
from unittest.mock import create_autospec, Mock

from spruned.daemon.electrod.electrod_connection import ElectrodConnectionPool
from spruned.daemon.tasks.fee_estimation import EstimateFeeConsensusProjector


class TestElectrumFeeEstimator(TestCase):
    def setUp(self):
        self._pool = create_autospec(ElectrodConnectionPool)
        self._repo = Mock()

    def tearDown(self):
        pass

    def test_projection(self):
        sut = EstimateFeeConsensusProjector()
        data = [

                {
                    "timestamp": 123456,
                    "value": 1000,
                    "peer": "1.2.3.4"
                },
                {
                    "timestamp": 123456,
                    "value": 998,
                    "peer": "1.2.3.4"
                },
                {
                    "timestamp": 123456,
                    "value": 997,
                    "peer": "1.2.3.4"
                },
                {
                    "timestamp": 123456,
                    "value": 1300,
                    "peer": "1.2.3.4"
                },
                {
                    "timestamp": 123456,
                    "value": 1090,
                    "peer": "1.2.3.4"
                }
        ]
        self.assertEqual(
            {
                'agreement': 80,
                'points': [1000, 998, 997, 1300, 1090],
                'value': 1000,
                'timestamp': 123456,
                'disagree': ['1.2.3.4'],
                'agree': True
            },
            sut.project(data, 5)
        )
