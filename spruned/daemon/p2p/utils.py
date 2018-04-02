import async_timeout
from pycoinnet.dnsbootstrap import dns_bootstrap_host_port_q
from pycoinnet.networks import MAINNET
import asyncio

from spruned.application.logging_factory import Logger


async def dns_bootstrap_servers(network=MAINNET, howmany=50):  # pragma: no cover
    host_q = dns_bootstrap_host_port_q(network)
    ad = []
    while 1:
        item: asyncio.coroutine = host_q.get()
        try:
            async with async_timeout.timeout(1):
                peer = await item
        except asyncio.TimeoutError:
            try:
                item.close()
            except asyncio.CancelledError:
                Logger.p2p.debug('Cancelled')
            break
        ad.append(peer)
    return ad


