import asyncio
from spruned.builder import blocks_reactor, headers_reactor, jsonrpc_server
#from spruned.utils import lock_directory, check_network, unlock_directory

if __name__ == '__main__':  # pragma: no cover
    try:
        #check_network()
        #lock()
        loop = asyncio.get_event_loop()
        loop.create_task(headers_reactor.start())
        loop.create_task(blocks_reactor.start())
        loop.create_task(jsonrpc_server.start())

        loop.run_forever()
    finally:
        pass
        #unlock()