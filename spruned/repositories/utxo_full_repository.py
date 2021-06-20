import asyncio
from concurrent.futures.thread import ThreadPoolExecutor
from enum import Enum

import typing

import rocksdb

from spruned.application.tools import dblsha256
from spruned.reactors.reactor_types import DeserializedBlock
from spruned.repositories import exceptions
from spruned.repositories.utxo_diskdb import UTXODiskDB


class DBPrefix(Enum):
    DB_VERSION = 1
    CURRENT_BLOCK_HEIGHT = 2
    UTXO = 3
    UTXO_REVERTS = 4
    UTXO_BY_SHARD = 5


class UTXOXOFullRepository:
    def __init__(
        self,
        db: rocksdb.DB,
        disk_db: UTXODiskDB,
        shards: typing.Optional[int] = 1000
    ):
        self.db = db
        self.loop = asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=32)
        self._best_header = None
        self._disk_db = disk_db
        self._safe_height = 0
        self._shards = shards

    def set_safe_height(self, safe_height: int):
        self._safe_height = safe_height

    @staticmethod
    def _get_db_key(prefix: DBPrefix, name: bytes = b''):
        assert isinstance(name, bytes)
        return b'%s%s' % (int.to_bytes(prefix.value, 2, "big"), name)

    async def process_blocks(self, blocks: typing.List[DeserializedBlock]):
        return await self.loop.run_in_executor(
            self.executor,
            self._process_blocks,
            blocks
        )

    def _process_blocks(self, blocks: typing.List[DeserializedBlock]):
        revert_utxo = []
        session = rocksdb.WriteBatch()
        pending = dict()
        for block in blocks:
            height_in_bytes = block.block.height.to_bytes(4, 'little')
            for tx in block.deserialized['txs']:
                if not tx['gen']:
                    for vin in tx['ins']:
                        revert_utxo.append(
                            self._spend_utxo(
                                session,
                                vin,
                                safe=block.block.height < self._safe_height,
                                pending=pending
                            )
                        )
                for i, vout in enumerate(tx['outs']):
                    utxo = self._add_utxo(session, vout, tx, i, height_in_bytes, tx['gen'])
                    pending[utxo[0]] = utxo[1]
            session.put(
                self._get_db_key(DBPrefix.CURRENT_BLOCK_HEIGHT),
                block.block.height.to_bytes(4, 'little')
            )
            self._disk_db.save_revert_state(block.block.hash, revert_utxo)
        self.db.write(session)
        return True

    async def revert_block(self, block: DeserializedBlock):
        return await self.loop.run_in_executor(
            self.executor,
            self._revert_block,
            block,
        )

    def _revert_block(self, block: DeserializedBlock) -> bool:
        raise NotImplementedError

    def _verify_utxo(self, vin: typing.Dict, utxo_key: bytes, pending: typing.Dict) -> bytes:
        # todo full validation
        existing = pending.get(utxo_key, None) or self.db.get(utxo_key)
        if existing is None:
            raise exceptions.UTXOInconsistencyException('utxo %s does not exist' % utxo_key)
        return existing

    def _spend_utxo(self, session: rocksdb.WriteBatch, vin, safe=True, pending: typing.Optional[dict] = None) -> bytes:
        outpoint = vin['hash'] + vin['index']
        utxo_key = self._get_db_key(DBPrefix.UTXO, outpoint)
        existing = None if safe else self._verify_utxo(vin, utxo_key, pending)
        session.delete(utxo_key)
        pending.pop(utxo_key, None)
        if self._shards:
            shard = (int.from_bytes(dblsha256(existing[13:]), 'little') % self._shards).to_bytes(4, 'little')
            session.delete(self._get_db_key(DBPrefix.UTXO_BY_SHARD, shard + outpoint))
        return existing

    def _backup_utxo_for_rollback(self, session, existing: bytes, utxo_key: bytes):
        session: rocksdb.WriteBatch
        session.put(
            self._get_db_key(DBPrefix.UTXO_REVERTS, utxo_key[2:]),
            existing
        )

    def _add_utxo(
            self,
            session: rocksdb.WriteBatch,
            vout: typing.Dict,
            tx: typing.Dict,
            i: int,
            block_height: bytes,
            is_coinbase: bool
    ) -> typing.Tuple:
        outpoint = tx['hash'] + i.to_bytes(4, 'little')
        utxo_key = self._get_db_key(DBPrefix.UTXO, outpoint)
        utxo_data = vout['amount'] + is_coinbase.to_bytes(1, 'little') + block_height + vout['script']
        session.put(utxo_key, utxo_data)
        if not self._shards:
            return utxo_key, utxo_data
        shard = (int.from_bytes(dblsha256(vout['script']), 'little') % self._shards).to_bytes(2, 'little')
        session.put(self._get_db_key(DBPrefix.UTXO_BY_SHARD, shard + outpoint), b'\x01')
        return utxo_key, utxo_data

    def get_utxo(self, txid: bytes, index: int) -> bool:
        pass
