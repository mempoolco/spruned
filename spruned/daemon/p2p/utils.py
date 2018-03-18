from pycoinnet.dnsbootstrap import dns_bootstrap_host_port_q
from pycoinnet.networks import MAINNET
import asyncio


async def dns_bootstrap_servers(network=MAINNET, howmany=50):
    host_q = dns_bootstrap_host_port_q(network)
    ad = []
    while 1:
        ad.append(host_q.get())
        if len(ad) > howmany:
            break

    return await asyncio.gather(*ad)
