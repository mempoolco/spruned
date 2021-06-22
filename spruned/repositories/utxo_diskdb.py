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

from spruned.dependencies.pybitcointools import serialize_script, deserialize_script


class UTXODiskDB:
    def __init__(self, path: str):
        self.path = Path(path)
        self._shard = 1000

    def _get_block_path(self, block_hash: bytes) -> Path:
        path = self.path / str(int.from_bytes(block_hash, 'big') % self._shard)
        return path

    @staticmethod
    def _get_block_revert_file(path: Path, block_hash: bytes) -> str:
        return f'{str(path)}/{block_hash.hex()}-rev.dat'

    def save_revert_state(self, block_hash: bytes, utxo: typing.List[bytes]) -> bool:
        revert_state = serialize_script(utxo)
        path = self._get_block_path(block_hash)
        path.mkdir(exist_ok=True, parents=True)
        with open(self._get_block_revert_file(path, block_hash), 'wb') as f:
            f.write(revert_state)
        return True

    def remove_revert_state(self, *block_hash: bytes) -> bool:
        for block_hash in block_hash:
            os.remove(path=self._get_block_revert_file(self._get_block_path(block_hash), block_hash))
        return True

    def get_revert_state(self, block_hash: bytes) -> typing.List[bytes]:
        path = self._get_block_path(block_hash)
        with open(self._get_block_revert_file(path, block_hash), 'rb') as f:
            return deserialize_script(f.read())
