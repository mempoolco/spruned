import asyncio
import shutil
import time
from pathlib import Path
from unittest import IsolatedAsyncioTestCase
from unittest.mock import Mock

from spruned.application.database import init_rocksdb_storage
from spruned.reactors.reactor_types import DeserializedBlock
from spruned.repositories.utxo_diskdb import UTXODiskDB
from spruned.repositories.utxo_multiprocessing_repository import UTXOXOFullRepository


class UTXORepositoryTestCase(IsolatedAsyncioTestCase):
    def _init_leveldb(self):
        sess = getattr(self, 'session', None)
        if sess:
            self.session.close()
            while not self.session.close:
                time.sleep(1)
        self.session = init_rocksdb_storage('/tmp/spruned_tests/utxo_repository')
        if getattr(self, 'sut', None):
            self.sut.leveldb = self.session
        return self.session

    def _init_sut(self):
        self.sut = UTXOXOFullRepository(self.session, '/tmp/spruned_tests/utxo_repository', self.diskdb)
        return self.sut

    def setUp(self):
        self.loop = asyncio.get_event_loop()
        self.path = Path('/tmp/spruned_tests')
        self.path.mkdir(exist_ok=True)
        self.diskdb = UTXODiskDB(str(self.path) + '/utxodata')
        self.session = self._init_leveldb()
        self.sut = self._init_sut()

    def tearDown(self):
        shutil.rmtree(self.path.__str__())

    async def test(self):
        blocks = [
            DeserializedBlock(
                block=Mock(
                    height=10,
                    hash=b'block10'
                ),
                deserialized={
                    'txs': [
                        {
                            'hash': b'tx0',
                            'gen': True,
                            'ins': [
                                {
                                    'hash': b'0'*32,
                                    'index': None,
                                    'script': b'script',
                                    'witness': b'witness'
                                }
                            ],
                            'outs': [
                                {
                                    'script': b'script10a',
                                    'amount': int(1000000).to_bytes(8, 'little')
                                }
                            ]
                        }
                    ]
                }
            ),
            DeserializedBlock(
                block=Mock(
                    height=11,
                    hash=b'block11'
                ),
                deserialized={
                    'txs': [
                        {
                            'hash': b'tx1',
                            'gen': True,
                            'ins': [
                                {
                                    'hash': b'0'*32,
                                    'index': None,
                                    'script': b'script',
                                    'witness': b'witness'
                                }
                            ],
                            'outs': [
                                {
                                    'script': b'script10a',
                                    'amount': int(1000000).to_bytes(8, 'little')
                                }
                            ]
                        }
                    ]
                }
            ),
            DeserializedBlock(
                block=Mock(
                    height=12,
                    hash=b'block12'
                ),
                deserialized={
                    'txs': [
                        {
                            'hash': b'tx2',
                            'gen': True,
                            'ins': [
                                {
                                    'hash': b'0'*32,
                                    'index': None,
                                    'script': b'script',
                                    'witness': b'witness'
                                }
                            ],
                            'outs': [
                                {
                                    'script': b'script10a',
                                    'amount': int(1000000).to_bytes(8, 'little')
                                }
                            ]
                        },
                        {
                            'hash': b'tx3',
                            'gen': False,
                            'ins': [
                                {
                                    'hash': b'tx1',
                                    'index': int(0).to_bytes(4, 'little'),
                                    'script': b'script',
                                    'witness': b'witness'
                                }
                            ],
                            'outs': [
                                {
                                    'script': b'script10a',
                                    'amount': int(400000).to_bytes(8, 'little')
                                },
                                {
                                    'script': b'script11a',
                                    'amount': int(600000).to_bytes(8, 'little')
                                }
                            ]
                        }
                    ]
                }
            ),
            DeserializedBlock(
                block=Mock(
                    height=13,
                    hash=b'block13'
                ),
                deserialized={
                    'txs': [
                        {
                            'hash': b'tx4',
                            'gen': True,
                            'ins': [
                                {
                                    'hash': b'0'*32,
                                    'index': None,
                                    'script': b'script',
                                    'witness': b'witness'
                                }
                            ],
                            'outs': [
                                {
                                    'script': b'script10a',
                                    'amount': int(1000000).to_bytes(8, 'little')
                                }
                            ]
                        },
                        {
                            'hash': b'tx4b',
                            'gen': False,
                            'ins': [
                                {
                                    'hash': b'tx3',
                                    'index': int(1).to_bytes(4, 'little'),
                                    'script': b'script',
                                    'witness': b'witness'
                                }
                            ],
                            'outs': [
                                {
                                    'script': b'script10a',
                                    'amount': int(400000).to_bytes(8, 'little')
                                }
                            ]
                        }
                    ]
                }
            ),
            DeserializedBlock(
                block=Mock(
                    height=14,
                    hash=b'block14'
                ),
                deserialized={
                    'txs': [
                        {
                            'hash': b'tx5',
                            'gen': True,
                            'ins': [
                                {
                                    'hash': b'0'*32,
                                    'index': None,
                                    'script': b'script',
                                    'witness': b'witness'
                                }
                            ],
                            'outs': [
                                {
                                    'script': b'script10a',
                                    'amount': int(1000000).to_bytes(8, 'little')
                                }
                            ]
                        }
                    ]
                }
            ),
            DeserializedBlock(
                block=Mock(
                    height=15,
                    hash=b'block15'
                ),
                deserialized={
                    'txs': [
                        {
                            'hash': b'tx6',
                            'gen': True,
                            'ins': [
                                {
                                    'hash': b'0'*32,
                                    'index': None,
                                    'script': b'script',
                                    'witness': b'witness'
                                }
                            ],
                            'outs': [
                                {
                                    'script': b'script10a',
                                    'amount': int(1000000).to_bytes(8, 'little')
                                }
                            ]
                        }
                    ]
                }
            )
        ]
        await self.sut.process_blocks([x.deserialized for x in blocks])
