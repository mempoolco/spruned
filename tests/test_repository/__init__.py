import asyncio
import shutil
import time
from pathlib import Path
from unittest import IsolatedAsyncioTestCase

from spruned.application.database import init_ldb_storage, init_disk_db
from spruned.repositories.chain_repository import BlockchainRepository


class RepositoryTestCase(IsolatedAsyncioTestCase):
    def _init_leveldb(self):
        sess = getattr(self, 'session', None)
        if sess:
            self.session.close()
            while not self.session.close:
                time.sleep(1)
        self.session = init_ldb_storage('/tmp/spruned_tests/chain_repository')
        if getattr(self, 'sut', None):
            self.sut.leveldb = self.session
        return self.session

    def _init_sut(self):
        self.sut = BlockchainRepository(self.session)
        return self.sut

    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.path = Path('/tmp/spruned_tests')
        self.path.mkdir(exist_ok=True)
        self.session = self._init_leveldb()
        self.sut = self._init_sut()

    def tearDown(self):
        shutil.rmtree(self.path.__str__())
