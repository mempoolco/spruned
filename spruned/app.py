#!/usr/bin/env python3
# Copyright (C) 2018 Guido Dassori <guido.dassori@gmail.com>
#

import sys
sys.path.insert(0, './')

if sys.version < '3.5.2':
    raise ValueError('Python >= 3.5.2 is required (Found: %s)' % sys.version)

import argparse
import asyncio
from spruned.application.context import ctx

parser = argparse.ArgumentParser(
    description="A Bitcoin Lightweight Pseudonode",
    formatter_class=argparse.ArgumentDefaultsHelpFormatter
)
parser.add_argument(
    '--rpcuser',
    action='store', dest='rpcuser', default=ctx.rpcuser,
    help='Username for JSON-RPC connections'
)
parser.add_argument(
    '--rpcpassword',
    action='store', dest='rpcpassword', default=ctx.rpcpassword,
    help='Password for JSON-RPC connections'
)
parser.add_argument(
    '--rpcport',
    action='store', dest='rpcport', default=ctx.rpcport,
    help='Listen for JSON-RPC connections on <port> (default: 8332 or testnet: 18332)'
)
parser.add_argument(
    '--rpcbind',
    action='store', dest='rpcbind', default=ctx.rpcbind,
    help='Bind to given address to listen for JSON-RPC connections.'
)
parser.add_argument(
    '--datadir',
    action='store', dest='datadir', default=ctx.datadir,
    help='Specify data directory'
)
parser.add_argument(
    '--daemon',
    action='store_true', dest='daemonize', default=bool(ctx.daemonize),
    help='Run in the background as a daemon and accept commands'
)
parser.add_argument(
    '--keep-blocks',
    action='store', dest='keep_blocks', default=int(ctx.keep_blocks),
    help='', type=int
)
parser.add_argument(
    '--network',
    action='store', dest='network',
    choices=[
        'bitcoin.mainnet',
        'bitcoin.testnet',
        #'bitcoin.regtest'
    ],
    help=''
)
parser.add_argument(
    '--debug',
    action='store_true', dest='debug', default=ctx.debug,
    help='Enable debug mode'
)
parser.add_argument(
    '--cache-size',
    action='store', dest='cache_size', default=int(ctx.cache_size),
    help='Cache size (in megabytes)'
)

args = parser.parse_args()
ctx.load_args(args)


def main():   # pragma: no cover
    args = parser.parse_args()
    ctx.load_args(args)
    from spruned import settings
    from spruned.application.tools import create_directory
    create_directory(ctx, settings.STORAGE_ADDRESS)

    from daemonize import Daemonize
    from spruned.main import main_task

    def start():  # pragma: no cover
        from spruned.application.logging_factory import Logger
        Logger.root.debug('Arguments: %s', args)
        main_loop = asyncio.get_event_loop()
        main_loop.create_task(main_task(main_loop))
        main_loop.run_forever()

    if args.daemonize:
        from spruned.application.logging_factory import Logger
        pid = ctx.datadir + '/spruned.pid'
        Logger.root.debug('Running spruned daemon')
        daemon = Daemonize(app="spruned", pid=pid, action=start, logger=Logger.root, auto_close_fds=False)
        daemon.start()
    else:
        start()


if __name__ == '__main__':  # pragma: no cover
    main()
