import asyncio
import shutil
import time
from pathlib import Path
from unittest import IsolatedAsyncioTestCase

from spruned.application.database import init_ldb_storage, init_disk_db
from spruned.repositories.chain_repository import BlockchainRepository


class RepositoryTestCase(IsolatedAsyncioTestCase):
    async def _run_diskdb(self, expect_failure=''):
        async def _handle_run():
            try:
                await self.diskdb.run()
            except Exception as e:
                if expect_failure:
                    self.assertTrue(expect_failure in str(e))

        self.loop.create_task(_handle_run(), name='aiodiskdb_main_loop')
        s = time.time()
        while not self.diskdb.running:
            await asyncio.sleep(0.01)
            self.assertLess(time.time() - s, 3, msg='timeout')

    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.path = Path('/tmp/spruned_tests')
        self.path.mkdir(exist_ok=True)
        self.session = init_ldb_storage('/tmp/spruned_tests/chain_repository')
        self.diskdb = init_disk_db('/tmp/spruned_tests/disk_database')
        self.sut = BlockchainRepository(self.diskdb, self.session)

    def tearDown(self):
        shutil.rmtree(self.path.__str__())
