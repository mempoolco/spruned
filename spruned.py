#!/usr/bin/env python3
# Copyright (C) 2018 Guido Dassori <guido.dassori@gmail.com>
#

import argparse
import asyncio

from spruned.application import tools
#from spruned.main import main_task

parser = argparse.ArgumentParser(
    description="A Bitcoin Lightweight Pseudonode",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter
)
parser.add_argument(
    '--rpcuser',
    action='store', dest='rpcuser', default="rpcuser",
    help='Username for JSON-RPC connections'
)
parser.add_argument(
    '--rpcpassword',
    action='store', dest='rpcpassword', default="rpcpassword",
    help='Password for JSON-RPC connections'
)
parser.add_argument(
    '--rpcport',
    action='store', dest='rpcport', default="8332",
    help='Listen for JSON-RPC connections on <port> (default: 8332 or testnet: 18332)'
)
parser.add_argument(
    '--rpcbind',
    action='store', dest='rpcbind', default="127.0.0.1",
    help='Bind to given address to listen for JSON-RPC connections.'
)
parser.add_argument(
    '--datadir',
    action='store', dest='datadir', default="~/.spruned",
    help='Specify data directory'
)
parser.add_argument(
    '--daemon',
    action='store_true', dest='daemonize', default=False,
    help='Run in the background as a daemon and accept commands'
)


if __name__ == '__main__':  # pragma: no cover
    args = parser.parse_args()
    print(args)
    tools.load_config(args)
    #main_loop = asyncio.get_event_loop()
    #main_loop.create_task(main_task(main_loop))
    #main_loop.run_forever()
