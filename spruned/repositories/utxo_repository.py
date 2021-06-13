import asyncio
import time
from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum

import typing
from functools import partial

import plyvel

from spruned.application import exceptions
from spruned.application.logging_factory import Logger
from spruned.application.tools import blockheader_to_blockhash
from spruned.repositories.repository_types import Block, BlockHeader


class UTXORepository:
    CURRENT_VERSION = 1

    def __init__(
        self,
        leveldb: plyvel.DB
    ):
        self.leveldb = leveldb
        self.loop = asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=64)
        self._best_header = None

    def add_utxo(self, txid: bytes, index: int, amount: int, script_hash: bytes):
        pass

    def get_utxo(self, txid: bytes, index: int) -> bool:
        pass

    def spend_utxo(self, txid: bytes, index: int) -> bool:
        pass

    def get_last_utxo_shard(self, shard_idx: int):
        pass

    def get_utxo_patches(self, shard_idx):
        pass
