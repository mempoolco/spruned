import asyncio
from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum

import plyvel

from spruned.repositories.repository_types import UTXO


class DBPrefix(Enum):
    DB_VERSION = 1
    CURRENT_BLOCK_HEIGHT = 2
    UTXO_INDEX = 3
    UTXO = 4
    SHARD = 5
    PATCH = 6


class UTXOXORepository:
    """
    Repository of the UTXOXO protocol <3.
    """

    def __init__(
        self,
        leveldb: plyvel.DB
    ):
        self.leveldb = leveldb
        self.loop = asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=64)
        self._best_header = None

    def add_utxo(self, utxo: UTXO):
        self.leveldb.put(

        )

    def add_utxos(self, *utxo: UTXO):
        pass

    def get_utxo(self, txid: bytes, index: int) -> bool:
        pass

    def spend_utxo(self, txid: bytes, index: int) -> bool:
        pass

    def get_last_utxo_shard(self, shard_idx: int):
        pass

    def get_utxo_patches(self, shard_idx: int, from_height: int):
        pass
