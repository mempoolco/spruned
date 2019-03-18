import logging
import sys
from spruned import settings
from spruned.application.context import ctx


class LoggingFactory:  # pragma: no cover
    def __init__(self, loglevel=logging.DEBUG, logfile=None, stdout=False):
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        root = logging.getLogger()
        root.setLevel(level=loglevel)

        file_logger = logfile and logging.FileHandler(logfile)
        stdout_logger = stdout and logging.StreamHandler(sys.stdout)

        stdout_logger and stdout_logger.setLevel(loglevel)
        stdout_logger and stdout_logger.setFormatter(formatter)
        stdout_logger and root.addHandler(stdout_logger)

        file_logger and file_logger.setLevel(loglevel)
        file_logger and file_logger.setFormatter(formatter)
        file_logger and root.addHandler(file_logger)

    @property
    def root(self):
        return logging.getLogger('root')

    @property
    def repository(self):
        return logging.getLogger('repository')

    @property
    def third_party(self):
        return logging.getLogger('third_party')

    @property
    def electrum(self):
        return logging.getLogger('electrum')

    @property
    def mempool(self):
        return logging.getLogger('mempool')

    @property
    def p2p(self):
        return logging.getLogger('p2p')

    @property
    def leveldb(self):
        return logging.getLogger('leveldb')

    @property
    def bitcoind(self):
        return logging.getLogger('bitcoind')

    @property
    def cache(self):
        return logging.getLogger('cache')

    @property
    def jsonrpc(self):
        return logging.getLogger('jsonrpc')

    @property
    def zmq(self):
        return logging.getLogger('zmq')


if settings.TESTING:
    Logger = LoggingFactory(
        logfile=None,
        loglevel=logging.DEBUG,
        stdout=True
    )  # type: LoggingFactory

elif ctx.debug:  # pragma: no cover
    logging.getLogger().setLevel(logging.DEBUG)
    logging.getLogger('root').setLevel(logging.DEBUG)
    logging.getLogger('jsonrpcserver.dispatcher.response').setLevel(logging.WARNING)
    logging.getLogger('pycoin').setLevel(logging.DEBUG)
    logging.getLogger('p2p').setLevel(logging.DEBUG)
    logging.getLogger('connectrum').setLevel(logging.DEBUG)
    logging.getLogger('electrum').setLevel(logging.DEBUG)
    logging.getLogger('mempool').setLevel(logging.DEBUG)
    logging.getLogger('cache').setLevel(logging.DEBUG)
    logging.getLogger('leveldb').setLevel(logging.DEBUG)
    logging.getLogger('asyncio').setLevel(logging.INFO)
    logging.getLogger('zmq').setLevel(logging.DEBUG)
    Logger = LoggingFactory(
        logfile=settings.LOGFILE,
        loglevel=logging.DEBUG,
        stdout=True
    )  # type: LoggingFactory

else:  # pragma: no cover
    logging.getLogger('jsonrpcserver.dispatcher.response').setLevel(logging.WARNING)
    logging.getLogger('jsonrpcserver.dispatcher.request').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    logging.getLogger('pycoin').setLevel(logging.ERROR)
    logging.getLogger('p2p').setLevel(logging.INFO)
    logging.getLogger('connectrum').setLevel(logging.ERROR)
    logging.getLogger('electrum').setLevel(logging.INFO)
    logging.getLogger('mempool').setLevel(logging.DEBUG)
    logging.getLogger('cache').setLevel(logging.INFO)
    logging.getLogger('leveldb').setLevel(logging.INFO)
    logging.getLogger('asyncio').setLevel(logging.CRITICAL)
    logging.getLogger('zmq').setLevel(logging.CRITICAL)
    Logger = LoggingFactory(
        logfile=settings.LOGFILE,
    )  # type: LoggingFactory
