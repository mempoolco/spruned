#
# Original is deprecated by Vitalik Buterin
# Using fork from Conio - https://github.com/Conio/pybitcointools
#
###################################################################################
#
# # Pybitcointools, Python library for Bitcoin signatures and transactions
#
#
# ### Advantages:
#
# * Functions have a simple interface, inputting and outputting in standard formats
# * No classes
# * Many functions can be taken out and used individually
# * Supports binary, hex and base58
# * Transaction deserialization format almost compatible with BitcoinJS
# * Electrum and BIP0032 support
# * Make and publish a transaction all in a single command line instruction
# * Includes non-bitcoin-specific conversion and JSON utilities
#
#
# This code is public domain. Everyone has the right to do whatever they want
# with it for any purpose.
#
# In case your jurisdiction does not consider the above disclaimer valid or
# enforceable, here's an MIT license for you:
#
# The MIT License (MIT)
#
# Copyright (c) 2013 Vitalik Buterin
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

import hashlib
import re
import binascii

string_types = (str)
string_or_bytes_types = (str, bytes)
int_types = (int, float)
# Base switching
code_strings = {
    2: '01',
    10: '0123456789',
    16: '0123456789abcdef',
    32: 'abcdefghijklmnopqrstuvwxyz234567',
    58: '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz',
    256: ''.join([chr(x) for x in range(256)])
}


def get_code_string(base):
    if base in code_strings:
        return code_strings[base]
    else:
        raise ValueError("Invalid base!")


def is_hexilified(tx):
    return isinstance(tx, str) and re.match('^[0-9a-fA-F]*$', tx)


def json_changebase(obj, changer):
    if isinstance(obj, string_or_bytes_types):
        return changer(obj)
    elif isinstance(obj, int_types) or obj is None:
        return obj
    elif isinstance(obj, list):
        return [json_changebase(x, changer) for x in obj]
    return dict((x, json_changebase(obj[x], changer)) for x in obj)


def encode(val, base, minlen=0):
    base, minlen = int(base), int(minlen)
    code_string = get_code_string(base)
    result_bytes = bytes()
    while val > 0:
        curcode = code_string[val % base]
        result_bytes = bytes([ord(curcode)]) + result_bytes
        val //= base

    pad_size = minlen - len(result_bytes)

    padding_element = b'\x00' if base == 256 else b'1' \
        if base == 58 else b'0'
    if pad_size > 0:
        result_bytes = padding_element*pad_size + result_bytes

    result_string = ''.join([chr(y) for y in result_bytes])
    result = result_bytes if base == 256 else result_string

    return result


def decode(string, base):
    if base == 256 and isinstance(string, str):
        string = bytes(bytearray.fromhex(string))
    base = int(base)
    code_string = get_code_string(base)
    result = 0
    if base == 256:
        def extract(d, cs):
            return d
    else:
        def extract(d, cs):
            return cs.find(d if isinstance(d, str) else chr(d))

    if base == 16:
        string = string.lower()
    while len(string) > 0:
        result *= base
        result += extract(string[0], code_string)
        string = string[1:]
    return result


def deserialize(tx):
    if is_hexilified(tx):
        return json_changebase(deserialize(binascii.unhexlify(tx)), lambda x: binascii.hexlify(x).decode())
    pos = [0]

    def read_as_int(bytez):
        pos[0] += bytez
        return decode(tx[pos[0]-bytez:pos[0]][::-1], 256)

    def read_var_int():
        pos[0] += 1

        val = tx[pos[0]-1]
        if val < 253:
            return val
        return read_as_int(pow(2, val - 252))

    def read_bytes(bytez):
        pos[0] += bytez
        return tx[pos[0]-bytez:pos[0]]

    def read_var_string():
        size = read_var_int()
        return read_bytes(size)

    obj = dict(ins=[], outs=[])
    obj["version"] = read_as_int(4)
    ins = read_var_int()
    segwit_flag = False
    if not ins:
        segwit_flag = read_var_int()
        ins = read_var_int()
    for i in range(ins):
        obj["ins"].append({
            "outpoint": {
                "hash": read_bytes(32)[::-1],
                "index": read_as_int(4)
            },
            "script": read_var_string(),
            "sequence": read_as_int(4)
        })
    outs = read_var_int()
    for i in range(outs):
        obj["outs"].append({
            "value": read_as_int(8),
            "script": read_var_string()
        })
    if segwit_flag:
        obj["segwit"] = True
        for i in range(ins):
            howmany = read_var_int()
            if howmany:
                obj['ins'][i]['txinwitness'] = [read_var_string() for x in range(0, howmany)]

    obj["locktime"] = read_as_int(4)
    return obj


def bin_sha256(string):
    binary_data = string if isinstance(string, bytes) else bytes(string, 'utf-8')
    return hashlib.sha256(binary_data).digest()


def json_is_base(obj, base):
    if isinstance(obj, bytes):
        return False
    alpha = get_code_string(base)
    if isinstance(obj, string_types):
        for i in range(len(obj)):
            if alpha.find(obj[i]) == -1:
                return False
        return True
    elif isinstance(obj, int_types) or obj is None:
        return True
    elif isinstance(obj, list):
        for i in range(len(obj)):
            if not json_is_base(obj[i], base):
                return False
        return True
    else:
        for x in obj:
            if not json_is_base(obj[x], base):
                return False
        return True


def from_int_to_byte(a):
    return bytes([a])


def num_to_var_int(x):
    x = int(x)
    if x < 253:
        return from_int_to_byte(x)
    elif x < 65536:
        return from_int_to_byte(253)+encode(x, 256, 2)[::-1]
    elif x < 4294967296:
        return from_int_to_byte(254) + encode(x, 256, 4)[::-1]
    else:
        return from_int_to_byte(255) + encode(x, 256, 8)[::-1]


def serialize(txobj):
    SEGWIT_MARKER = b'\x00'
    SEGWIT_FLAG = b'\x01'
    o = []
    if json_is_base(txobj, 16):
        json_changedbase = json_changebase(txobj, lambda x: binascii.unhexlify(x))
        return str(binascii.hexlify(serialize(json_changedbase)).decode())
    o.append(encode(txobj["version"], 256, 4)[::-1])
    segwit = txobj.get('segwit', False)
    o.append(num_to_var_int(len(txobj["ins"])))
    for inp in txobj["ins"]:
        inp['script'] = inp.get('script', '')
        segwit = bool(inp.get("txinwitness") != None) if not segwit else segwit
        o.append(inp["outpoint"]["hash"][::-1])
        o.append(encode(inp["outpoint"]["index"], 256, 4)[::-1])
        out_len = num_to_var_int(len(inp["script"]))
        script = inp['script'] if inp.get('script') else b''
        o.append(out_len + script)
        o.append(encode(inp.get('sequence', 4294967295), 256, 4)[::-1])
    o.append(num_to_var_int(len(txobj["outs"])))
    for out in txobj["outs"]:
        out['script'] = out['script']
        o.append(encode(out["value"], 256, 8)[::-1])
        o.append(num_to_var_int(len(out["script"]))+out["script"])
    if segwit:
        o.insert(1, SEGWIT_MARKER + SEGWIT_FLAG)
        for inp in txobj["ins"]:
            if not isinstance(inp.get('txinwitness', None), list):
                o.append(num_to_var_int(0))
            else:
                if len(inp.get('txinwitness')):
                    o.append(num_to_var_int(len(inp.get('txinwitness'))))
                    for i in inp.get('txinwitness'):
                        o.append(num_to_var_int(len(i)))
                        if i:
                            o.append(i)
                else:
                    o.append(num_to_var_int(2))
                    o.append(num_to_var_int(0) * 2)
    o.append(encode(txobj["locktime"], 256, 4)[::-1])
    return b''.join(o)


def address_to_script(addr):
    if addr[0] == '3' or addr[0] == '2':
        return mk_scripthash_script(addr)
    else:
        return mk_pubkey_script(addr)


def mk_pubkey_script(addr):
    # Keep the auxiliary functions around for altcoins' sake
    return '76a914' + b58check_to_hex(addr) + '88ac'


def mk_scripthash_script(addr):
    return 'a914' + b58check_to_hex(addr) + '87'


def b58check_to_hex(inp):
    return safe_hexlify(b58check_to_bin(inp))


def b58check_to_bin(inp):
    leadingzbytes = len(re.match('^1*', inp).group(0))
    data = b'\x00' * leadingzbytes + changebase(inp, 58, 256)
    assert bin_dbl_sha256(data[:-4])[:4] == data[-4:]
    return data[1:-4]


def changebase(string, frm, to, minlen=0):
    if frm == to:
        return lpad(string, get_code_string(frm)[0], minlen)
    return encode(decode(string, frm), to, minlen)


def lpad(msg, symbol, length):
    if len(msg) >= length:
        return msg
    return symbol * (length - len(msg)) + msg


def safe_hexlify(a):
    return binascii.hexlify(a).decode()


def bin_dbl_sha256(s):
    return hashlib.sha256(hashlib.sha256(s).digest()).digest()
