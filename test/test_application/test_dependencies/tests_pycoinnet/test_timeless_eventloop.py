import asyncio
import time
import unittest

from test.test_application.test_dependencies.tests_pycoinnet.pipes import create_direct_streams_pair, \
    create_direct_transport_pair
from test.test_application.test_dependencies.tests_pycoinnet.timeless_eventloop import TimelessEventLoop


def run(f):
    return asyncio.get_event_loop().run_until_complete(f)


class ATestProtocol(asyncio.Protocol):
    def __init__(self):
        self._loop = asyncio.get_event_loop()
        self.connection_made_time = None
        self.data_received_list = []
        self._base_time = time.time()

    def connection_made(self, transport):
        self.connection_made_time = self._loop.time()

    def data_received(self, data):
        now = self._loop.time() - self._base_time
        self.data_received_list.append((now, data))


class TheTest(unittest.TestCase):
    def setUp(self):
        asyncio.set_event_loop(TimelessEventLoop())

    def tearDown(self):
        asyncio.set_event_loop(asyncio.new_event_loop())

    def test_loop(self):
        loop = asyncio.get_event_loop()
        a1 = time.time()
        b1 = loop.time()
        run(asyncio.sleep(50))
        a2 = time.time()
        b2 = loop.time()
        assert a2 - a1 < 0.1
        assert b2 - b1 > 50.0

    def test_timeless_transport(self):
        loop = asyncio.get_event_loop()
        (t1, p1), (t2, p2) = create_direct_transport_pair(ATestProtocol)
        D1 = b"foo" * 300
        D2 = b"bar" * 100
        t1.write(D1)
        t2.write(D2)
        a1 = time.time()
        b1 = loop.time()
        run(asyncio.sleep(50))
        a2 = time.time()
        b2 = loop.time()
        assert a2 - a1 < 0.1
        assert b2 - b1 > 50.0
        d1 = b''.join(x[-1] for x in p1.data_received_list)
        assert d1 == D2
        d2 = b''.join(x[-1] for x in p2.data_received_list)
        assert d2 == D1

    def test_timeless_streams(self):
        (r1, w1), (r2, w2) = create_direct_streams_pair()
        w1.write(b"fooPlease kill me\nhello\n")
        w2.write(b"bar")
        a1 = time.time()
        d1 = run(r1.readexactly(3))
        d2 = run(r2.readexactly(3))
        assert d1 == b"bar"
        assert d2 == b"foo"
        l1 = run(r2.readline())
        assert l1 == b'Please kill me\n'
        l1 = run(r2.readline())
        assert l1 == b'hello\n'
        a2 = time.time()
        assert a2 - a1 < 0.1
