#
# https://github.com/richardkiss/pycoinnet/
#
# The MIT License (MIT)
#
# Copyright (c) 2014 Richard Kiss
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

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
