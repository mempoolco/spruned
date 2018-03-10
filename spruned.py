import asyncio

from spruned.application.tools import load_config
from spruned.builder import electrod_daemon, jsonrpc_server

if __name__ == '__main__':
    load_config()
    loop = asyncio.get_event_loop()
    loop.create_task(electrod_daemon.start())
    loop.create_task(jsonrpc_server.start())
    loop.run_forever()
