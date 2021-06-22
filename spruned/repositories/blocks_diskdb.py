# The MIT License (MIT)
#
# Copyright (c) 2021 - spruned contributors - https://github.com/mempoolco/spruned
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import os
from pathlib import Path
import typing
from spruned.repositories.repository_types import Block


class BlocksDiskDB:
    def __init__(self, path: str):
        self.path = Path(path)
        self._shard = 1000

    def _get_block_path(self, block_hash: bytes) -> Path:
        path = self.path / str(int.from_bytes(block_hash, 'big') % self._shard)
        return path

    @staticmethod
    def _get_block_file(path: Path, block_hash: bytes) -> str:
        return f'{str(path)}/{block_hash.hex()}.dat'

    @staticmethod
    def _get_block_revert_file(path: Path, block_hash: bytes) -> str:
        return f'{str(path)}/{block_hash.hex()}-rev.dat'

    def add(self, *blocks: Block):
        for block in blocks:
            path = self._get_block_path(block.hash)
            path.mkdir(exist_ok=True, parents=True)
            with open(self._get_block_file(path, block.hash), 'wb') as f:
                f.write(block.data)
        return True

    def get_block(self, block_hash: bytes) -> typing.Optional[bytes]:
        assert isinstance(block_hash, bytes)
        try:
            with open(self._get_block_file(self._get_block_path(block_hash), block_hash), 'rb') as f:
                return f.read()
        except FileNotFoundError:
            return

    def get_block_chunk(self, block_hash: bytes, position: int, size: int) -> typing.Optional[bytes]:
        try:
            with open(self._get_block_file(self._get_block_path(block_hash), block_hash), 'rb') as f:
                f.seek(position)
                tx_data = f.read(size)
        except FileNotFoundError:
            return
        return tx_data

    def remove_block(self, *block_hash: bytes):
        for block_hash in block_hash:
            os.remove(path=self._get_block_file(self._get_block_path(block_hash), block_hash))
