import asyncio
from spruned.dependencies.pycoinnet.MappingQueue import MappingQueue


def dns_bootstrap_host_port_q(network, getaddrinfo=asyncio.get_event_loop().getaddrinfo):
    """
    Accepts network type and returns an asyncio.Queue, which is loads with tuples of the
    form (host, port). When it runs out, it puts a "None" to terminate.
    """

    async def flatten(items, q):
        for item in items:
            await q.put(item)

    hosts_seen = set()

    async def getaddr(dns_host, q):
        responses = await getaddrinfo(dns_host, network.default_port)
        for response in responses:
            host = response[-1][:2]
            if host not in hosts_seen:
                hosts_seen.add(host)
                await q.put(host)

    filters = [
        dict(callback_f=flatten),
        dict(callback_f=getaddr),
    ]
    q = MappingQueue(*filters)
    q.put_nowait(network.dns_bootstrap)
    return q
