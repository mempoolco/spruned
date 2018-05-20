import asyncio
import unittest

from spruned.dependencies.pycoinnet.dnsbootstrap import dns_bootstrap_host_port_q
from spruned.dependencies.pycoinnet.networks import MAINNET


def make_getaddrinfo():
    counter = 0

    @asyncio.coroutine
    def fake_getaddrinfo(*args):
        nonlocal counter
        r = []
        for _ in range(10):
            item = ["family", "type", "proto", "canonname", ("192.168.1.%d" % counter, 8333)]
            r.append(item)
            counter += 1
        return r
    return fake_getaddrinfo


class DNSBootstrapTest(unittest.TestCase):
    def test1(self):
        q = dns_bootstrap_host_port_q(MAINNET, getaddrinfo=make_getaddrinfo())
        for _ in range(10 * len(MAINNET.dns_bootstrap)):
            r = asyncio.get_event_loop().run_until_complete(q.get())
            self.assertEqual(r, ("192.168.1.%d" % _, 8333))
        q.cancel()
