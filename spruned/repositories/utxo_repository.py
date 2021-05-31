import asyncio
from dataclasses import dataclass

import typing
from enum import Enum


@dataclass
class Outpoint:
    txid: bytes
    index: int

    def serialize(self) -> bytes:
        return self.txid + self.index.to_bytes(2, 'little')

    @classmethod
    def deserialize(cls, data: bytes):
        return cls(
            txid=data[:32],
            index=int.from_bytes(data[32:], 'little')
        )


@dataclass
class Unspent:
    outpoint: Outpoint
    script: bytes
    amount: typing.Optional[int] = None

    @classmethod
    def deserialize(cls, outpoint: Outpoint, data: typing.Dict):
        return cls(
            outpoint=outpoint,
            amount=data['amount'],
            script=data['script']
        )


class Spend:
    outpoint: Outpoint
    script: typing.Optional[bytes]
    witness: typing.List[bytes]


class BlockUnspents:
    unspents: typing.Iterable[Unspent]
    height: int


class BlockSpends:
    spends: typing.Iterable[Spend]
    height: int


class Command(Enum):
    ADD = 0
    REM = 1


class UTXODataTypes(Enum):
    SCRIPT = 0
    AMOUNT = 1
    BLOCK_HEIGHT = 2


class DBPrefix(Enum):
    UTXO_BY_SCRIPT = 0
    UTXO_BY_OUTPOINT = 1
    BEST_HEIGHT = 2


class UTXORepository:
    def __init__(self, leveldb_session, max_cached_entries=1000000):
        self._max_height: typing.Dict[Command:int] = {Command.ADD: 0, Command.REM: 0}
        self._utxo_by_outpoint: typing.Dict[bytes:typing.Dict[str:bytes]] = dict()
        self._idx_by_script: typing.Dict[bytes:typing.List[bytes]] = dict()
        self._removed_by_outpoint: typing.Set[bytes] = set()
        self._stack: typing.List[typing.List[Command, str]] = list()
        self._lock = asyncio.Lock()
        self.session = leveldb_session
        self._max_cached_entries = max_cached_entries

    def _get_db_key(self, db_data_type: DBPrefix, val: bytes):
        pass

    async def get_max_height(self):
        pass

    def _append(self, cmd: Command, key: bytes):
        self._stack.append([cmd, key])

    async def parse_block(self, block: typing.Dict):
        pass

    async def add(self, unspents: BlockUnspents):
        assert unspents.height == self._max_height[Command.ADD] + 1
        await self._lock.acquire()
        for unspent in unspents.unspents:
            ser = unspent.outpoint.serialize()
            self._append(Command.ADD, ser)
            self._utxo_by_outpoint[ser] = {
                UTXODataTypes.SCRIPT: unspent.script,
                UTXODataTypes.AMOUNT: unspent.amount,
                UTXODataTypes.BLOCK_HEIGHT: unspents.height
            }
            self._idx_by_script[unspent.script] = ser
        self._max_height[Command.ADD] += 1
        self._lock.release()

    async def remove(self, spends: BlockSpends):
        assert spends.height == self._max_height[Command.REM] + 1
        await self._lock.acquire()
        for spend in spends.spends:
            ser = spend.outpoint.serialize()
            self._append(Command.REM, ser)
            self._removed_by_outpoint.add(ser)
            unspent = self._utxo_by_outpoint.pop(ser, None)
            unspent and self._idx_by_script.pop(unspent[UTXODataTypes.SCRIPT])
        self._max_height[Command.REM] += 1
        self._lock.release()

    async def get(self, outpoint: Outpoint):
        if outpoint in self._removed_by_outpoint:
            return
        cached = self._utxo_by_outpoint.get(outpoint.serialize())
        if cached:
            return Unspent.deserialize(outpoint, cached)
        self.session.get(
            self._get_db_key(DBPrefix.UTXO_BY_OUTPOINT, outpoint.serialize())
        )

    async def get_many_by_script(self, script: str):
        pass

    async def persist_data(self):
        await self._lock.acquire()
        # write changes to disk
        self._lock.release()
