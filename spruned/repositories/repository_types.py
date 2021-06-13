from dataclasses import dataclass

import typing
from aiodiskdb import ItemLocation


@dataclass
class BlockHeader:
    data: bytes
    height: int
    hash: bytes

    @property
    def prev_block_hash(self):
        return self.data and self.data[4:36][::-1]


@dataclass
class Block:
    hash: bytes
    data: bytes
    height: int
    location: typing.Optional[ItemLocation] = None

    @property
    def header(self):
        return BlockHeader(
            data=self.data[:80],
            height=self.height,
            hash=self.hash
        )

