import asyncio
from spruned.builder import daemon, jsonrpc_server

if __name__ == '__main__':  # pragma: no cover
    loop = asyncio.get_event_loop()
    loop.create_task(daemon.start())
    loop.create_task(jsonrpc_server.start())

    loop.run_forever()
