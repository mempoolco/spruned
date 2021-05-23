import itertools

from spruned.dependencies.pycoinnet.networks import TESTNET
import asyncio


async def dns_bootstrap_servers(network=TESTNET):  # pragma: no cover
    hosts = set()
    fn = asyncio.get_event_loop().getaddrinfo
    done, pending = await asyncio.wait(
        map(
            lambda x: fn(x, network.default_port),
            network.dns_bootstrap,
        ),
        timeout=2
    )
    for f in itertools.chain(done, pending):
        hosts.update(
            set(
                map(
                    lambda r: (r[4][0], r[4][1]),
                    f.result()
                )
            )
        ) if f.done() else f.cancel()
    return hosts
