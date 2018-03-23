import logging
import sys
from spruned.application import settings


class LoggingFactory:
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
        return logging.getLogger('bitcoind')


if settings.TESTING:
    Logger = LoggingFactory(
        logfile=None,
        loglevel=logging.DEBUG,
        stdout=True
    )  # type: LoggingFactory

elif settings.DEBUG:
    logging.getLogger('jsonrpcserver.dispatcher.response').setLevel(logging.WARNING)
    Logger = LoggingFactory(
        logfile=settings.LOGFILE,
        loglevel=logging.DEBUG,
        stdout=True
    )  # type: LoggingFactory

else:
    logging.getLogger('jsonrpcserver.dispatcher.response').setLevel(logging.WARNING)
    logging.getLogger('aiohttp.access').setLevel(logging.WARNING)
    logging.getLogger('connectrum').setLevel(logging.WARNING)
    logging.getLogger('pycoin').setLevel(logging.WARNING)
    logging.getLogger('p2p').setLevel(logging.WARNING)
    Logger = LoggingFactory(
        logfile=settings.LOGFILE,
        loglevel=logging.INFO,
        stdout=False
    )  # type: LoggingFactory
