import logging
import sys

import os

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
    def bitcoind(self):
        return logging.getLogger('bitcoind')


Logger = LoggingFactory(
    logfile=settings.LOGFILE if not os.getenv('TESTING') else None,
    loglevel=(settings.DEBUG and logging.DEBUG or logging.INFO) if not os.getenv('TESTING') else logging.DEBUG,
    stdout=True
)  # type: LoggingFactory

logging.getLogger('connectrum').setLevel(logging.WARNING)
