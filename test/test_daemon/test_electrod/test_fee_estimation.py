import asyncio
from unittest import TestCase
from unittest.mock import Mock

from spruned.daemon.electrod.electrod_fee_estimation import EstimateFeeConsensusProjector, \
    EstimateFeeConsensusCollector


class TestElectrumFeeEstimator(TestCase):
    def setUp(self):
        self._servers_responses = {
            'peer1/s': {
                2: 0.0002,
                6: 0.0001,
                100: 0.00001
            },
            'peer2/s': {
                2: 0.0002,
                6: 0.0001,
                100: 0.00001
            },
            'peer3/s': {
                2: 99999,
                6: 0.0001,
                100: 0.00001
            }
        }
        self._repo = Mock()

    def _make_peer(self, hostname, protocol, **_):
        resp = self._servers_responses

        async def _get_data(resp, *a):
            peer = hostname + '/' + protocol
            response = resp[peer][a[1]]
            return response

        async def _connect(*a, **b):
            peer = hostname + '/' + protocol
            if peer not in self._servers_responses:
                raise ConnectionError
            return True
        connection = Mock()
        connection.connect.side_effect = _connect
        connection.disconnect_return_value = True
        connection.client.RPC.side_effect = lambda *a, **kw: _get_data(resp, *a, *kw)

        return connection

    def tearDown(self):
        pass

    def test_collector(self):
        sut = EstimateFeeConsensusCollector(connectionclass=self._make_peer)
        peers = list(self._servers_responses.keys())
        sut.add_peer(peers[0])
        sut.add_peer(peers[1])
        sut.add_peer(peers[2])
        sut.add_peer('meh/s')
        loop = asyncio.get_event_loop()
        loop.run_until_complete(sut.collect(rates=[2], members=3))
        if not sut.rates_available(3):
            loop.run_until_complete(sut.collect(rates=[2], members=3))
        self.assertTrue(sut.rates_available(3))
        self.assertFalse(sut.rates_available(4))
        sut.add_rate(3)
        self.assertFalse(sut.rates_available(3))
        return sut

    def test_projection(self):
        sut = EstimateFeeConsensusProjector()
        collector = self.test_collector()
        data = collector.get_rates(2)
        projection = sut.project(data, members=3)
        points = projection.pop('points')
        self.assertEqual(
            {
                'agree': False,
                'agreement': 66,
                'average': 20,
                'average_satoshi_per_kb': 0.0002,
                'disagree': ['peer3/s'],
                'median': 20,
                'timestamp': data[0]['timestamp']
            },
            projection
        )
        self.assertEqual(
            sorted([20, 20, 9999900000]),
            sorted(points)
        )
        collector.reset_data()
        self.assertEqual(collector.get_rates(2), [])
