import asyncio
import unittest

from spruned.dependencies.pycoinnet.Peer import Peer
from spruned.dependencies.pycoinnet.networks import MAINNET
from spruned.dependencies.pycoinnet.version import version_data_for_peer

from test.test_application.test_dependencies.tests_pycoinnet.pipes import create_direct_streams_pair
from test.test_application.test_dependencies.tests_pycoinnet.timeless_eventloop import TimelessEventLoop


def run(f):
    return asyncio.get_event_loop().run_until_complete(f)


class PeerTest(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(TimelessEventLoop())

    def tearDown(self):
        asyncio.set_event_loop(asyncio.new_event_loop())

    def create_peer_pair(self):
        (r1, w1), (r2, w2) = create_direct_streams_pair()
        p1 = Peer(r1, w1, MAINNET.magic_header, MAINNET.parse_from_data, MAINNET.pack_from_data)
        p2 = Peer(r2, w2, MAINNET.magic_header, MAINNET.parse_from_data, MAINNET.pack_from_data)
        return p1, p2

    def test_Peer_blank_messages(self):
        p1, p2 = self.create_peer_pair()
        for t in ["verack", "getaddr", "mempool", "filterclear"]:
            t1 = p1.send_msg(t)
            t2 = run(p2.next_message(unpack_to_dict=False))
            assert t1 is None
            assert t2 == (t, b'')

    def test_Peer_version(self):
        p1, p2 = self.create_peer_pair()
        version_msg = version_data_for_peer(p1)
        version_msg["relay"] = True
        t1 = p1.send_msg("version", **version_msg)
        assert t1 is None
        t2 = run(p2.next_message())
        assert t2 == ("version", version_msg)

    def test_Peer_ping_pong(self):
        p1, p2 = self.create_peer_pair()
        for nonce in (1, 11, 111123, 8888888817129829):
            for t in "ping pong".split():
                d = dict(nonce=nonce)
                t1 = p1.send_msg(t, **d)
                assert t1 is None
                t1 = p2.send_msg(t, **d)
                assert t1 is None
                t2 = run(p2.next_message())
                assert t2 == (t, d)
                t2 = run(p1.next_message())
                assert t2 == (t, d)

    # TODO:
    # add tests for the following messages:
    """
    'addr': "date_address_tuples:[LA]",
    'getblocks': "version:L hashes:[#] hash_stop:#",
    'getheaders': "version:L hashes:[#] hash_stop:#",
    'tx': "tx:T",
    'block': "block:B",
    'headers': "headers:[zI]",
    'filterload': "filter:[1] hash_function_count:L tweak:L flags:b",
    'filteradd': "data:[1]",
    'merkleblock': (
    "header:z total_transactions:L hashes:[#] flags:[1]"
    ),
    'alert': "payload:S signature:S",
    """

    def test_disconnect(self):
        p1, p2 = self.create_peer_pair()
        for nonce in (1, 11, 111123, 8888888817129829):
            for t in "ping pong".split():
                d = dict(nonce=nonce)
                t1 = p1.send_msg(t, **d)
                assert t1 is None
                t1 = p2.send_msg(t, **d)
                assert t1 is None
                t2 = run(p2.next_message())
                assert t2 == (t, d)
                t2 = run(p1.next_message())
                assert t2 == (t, d)
        p2.send_msg("ping", nonce=100)
        t1 = run(p1.next_message())
        assert t1 == ("ping", dict(nonce=100))
        p2.send_msg("ping", nonce=100)
        p2.close()
        run(p1.next_message())
        with self.assertRaises(EOFError):
            run(p1.next_message())