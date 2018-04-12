from argparse import Namespace
import threading
from pathlib import Path
from typing import Dict
from spruned.application import networks


class Context(dict):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.update(
            {
                'args': {},
                'default': {
                    'daemonize': False,
                    'datadir': str(Path.home()) + '/.spruned',
                    'rpcbind': '127.0.0.1',
                    'rpcport': 8332,
                    'rpcuser': 'rpcuser',
                    'rpcpassword': 'rpcpassword',
                    'network': 'bitcoin.mainnet',
                    'debug': False,
                    'cache_size': 50,
                    'keep_blocks': 200
                }
            }
        )

    @property
    def datadir(self):
        return self._get_param('datadir')

    @property
    def debug(self):
        return self._get_param('debug')

    @property
    def keep_blocks(self):
        return int(self._get_param('keep_blocks'))

    @property
    def network(self):
        return self._get_param('network')

    @property
    def rpcbind(self):
        return self._get_param('rpcbind')

    @property
    def rpcport(self):
        return self._get_param('rpcport')

    @property
    def rpcuser(self):
        return self._get_param('rpcuser')

    @property
    def rpcpassword(self):
        return self._get_param('rpcpassword')

    @property
    def daemonize(self):
        return self._get_param('daemonize')

    @property
    def cache_size(self):
        return int(self._get_param('cache_size')) * 1024 * 1024

    def load_args(self, args: Namespace):
        self['args'] = {
            'daemonize': args.daemonize,
            'datadir': args.datadir,
            'rpcbind': args.rpcbind,
            'rpcpassword': args.rpcpassword,
            'rpcport': args.rpcport,
            'rpcuser': args.rpcuser,
            'network': args.network,
            'debug': args.debug,
            'cache_size': int(args.cache_size),
            'keep_blocks': int(args.keep_blocks)
        }
        self.apply_context()

    def _get_param(self, key):
        return self['args'].get(key, self['default'].get(key, None))

    def apply_context(self):
        pass

    def get_network(self) -> Dict:
        net, work = self._get_param('network').split('.')
        module = getattr(networks, net)
        return getattr(module, work)


_local = threading.local()
_local.ctx = ctx = Context()
