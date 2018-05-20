#
# https://github.com/richardkiss/pycoinnet/
#
# The MIT License (MIT)
#
# Copyright (c) 2014 Richard Kiss
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

import binascii

from collections import namedtuple

from pycoin.block import Block
from spruned.dependencies.pycoinnet.pycoin.make_parser_and_packer import (
    make_parser_and_packer, standard_messages,
    standard_message_post_unpacks, standard_streamer, standard_parsing_functions
)
from pycoin.tx.Tx import Tx

Network = namedtuple(
    'Network', (
        'code',
        'magic_header', 'dns_bootstrap', 'default_port', 'pack_from_data',
        'parse_from_data'
    )
)

streamer = standard_streamer(standard_parsing_functions(Block, Tx))
btc_parser, btc_packer = make_parser_and_packer(
    streamer, standard_messages(), standard_message_post_unpacks(streamer))


MAINNET = Network(
    'BTC', binascii.unhexlify('F9BEB4D9'), [
        "seed.bitcoin.sipa.be", "dnsseed.bitcoin.dashjr.org",
        "bitseed.xf2.org", "dnsseed.bluematt.me",
    ],
    8333,
    btc_packer,
    btc_parser,
)

TESTNET = Network(
    'XTC', binascii.unhexlify('0B110907'), [
        "testnet-seed.bitcoin.jonasschnelli.ch"
    ],
    18333,
    btc_packer,
    btc_parser,
)

REGTEST = Network(
    'XTC', binascii.unhexlify('fabfb5da'), [],
    18444,
    btc_packer,
    btc_parser,
)

NETWORKS = [MAINNET, TESTNET, REGTEST]
