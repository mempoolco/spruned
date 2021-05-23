# https://github.com/richardkiss/pycoin
#
# The MIT License (MIT)
#
# Copyright (c) 2013 by Richard Kiss
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

import functools

from pycoin.encoding.hexbytes import b2h_rev
from pycoin.satoshi.satoshi_struct import stream_struct, parse_struct

ITEM_TYPE_TX = 1
ITEM_TYPE_BLOCK = 2
ITEM_TYPE_MERKLEBLOCK = 3
ITEM_TYPE_COMPACTBLOCK = 4
ITEM_TYPE_WTX = 5

ITEM_TYPE_SEGWIT_TX = 1073741825
ITEM_TYPE_SEGWIT_BLOCK = 1073741826


BLOCK = "Block"
TX = "Tx"
MERKLE = "Merkleblock"
HEADER = "BlockHeader"


@functools.total_ordering
class InvItem(object):
    def __init__(self, item_type, data):
        assert item_type in (
            ITEM_TYPE_TX,
            ITEM_TYPE_BLOCK,
            ITEM_TYPE_MERKLEBLOCK,
            ITEM_TYPE_COMPACTBLOCK,
            ITEM_TYPE_SEGWIT_TX,
            ITEM_TYPE_SEGWIT_BLOCK,
            ITEM_TYPE_WTX,
        )
        self.item_type = item_type
        assert isinstance(data, bytes)
        assert not len(data) % 32
        self.data = data

    def __str__(self):
        inv_item_types = {
            0: "?",
            ITEM_TYPE_TX: TX,
            ITEM_TYPE_BLOCK: BLOCK,
            ITEM_TYPE_MERKLEBLOCK: MERKLE,
            ITEM_TYPE_COMPACTBLOCK: HEADER,
            ITEM_TYPE_SEGWIT_TX: TX,
            ITEM_TYPE_SEGWIT_BLOCK: BLOCK
        }
        idx = self.item_type
        if idx not in inv_item_types.keys():
            idx = 0
        return "InvItem %s [%s]" % (inv_item_types[idx], b2h_rev(self.data))

    def __repr__(self):
        return str(self)

    def __hash__(self):
        return hash((self.item_type, self.data))

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.item_type == other.item_type and self.data == other.data
        return False

    def __lt__(self, other):
        return (self.item_type, self.data) < (other.item_type, other.data)

    def stream(self, f):
        stream_struct("L#", f, self.item_type, self.data)

    @classmethod
    def parse(cls, f):
        return cls(*parse_struct("L#", f))
