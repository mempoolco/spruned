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

from dataclasses import dataclass

import typing

INT4_MAX = 4294967295


@dataclass
class BlockHeader:
    data: bytes
    hash: bytes
    height: typing.Optional[int] = None

    @property
    def prev_block_hash(self):
        return self.data and self.data[4:36][::-1]

    def as_dict(self):
        return {
            'data': self.data,
            'height': self.height,
            'hash': self.hash
        }


@dataclass
class Block:
    hash: bytes
    data: bytes
    height: int

    @property
    def header(self):
        return BlockHeader(
            data=self.data[:80],
            height=self.height,
            hash=self.hash
        )

    @property
    def size(self):
        return len(self.data)


@dataclass
class UTXO:
    hash: bytes
    height: int
    amount: int
    script: bytes
    witness: bytes
