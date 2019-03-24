import asyncio
import time
import re
from spruned.dependencies.pybitcointools import decode, bin_sha256, encode
from spruned.application import exceptions
import hashlib
import binascii


def blockheader_to_blockhash(header: (bytes, str), fmt=None) -> (bytes, str):
    if isinstance(header, bytes):
        h, fmt = header, fmt or 'bin'
    else:
        h, fmt = binascii.unhexlify(header.encode()), fmt or 'hex'
    blockhash = hashlib.sha256(hashlib.sha256(h).digest())
    bytes_blockhash = blockhash.digest()[::-1]
    return fmt == 'hex' and binascii.hexlify(bytes_blockhash).decode() or bytes_blockhash


def deserialize_header(header: (str, bytes)):
    if isinstance(header, bytes):
        h, fmt = header, 'bin'
    else:
        h, fmt = binascii.unhexlify(header.encode()), 'hex'
    blockhash = bin_sha256(bin_sha256(h))[::-1]
    data = {
        "version": decode(h[:4][::-1], 256),
        "prev_block_hash": h[4:36][::-1],
        "merkle_root": h[36:68][::-1],
        "timestamp": decode(h[68:72][::-1], 256),
        "bits": decode(h[72:76][::-1], 256),
        "nonce": decode(h[76:80][::-1], 256),
        "hash": blockhash
    }
    if fmt == 'hex':
        data['prev_block_hash'] = binascii.hexlify(data['prev_block_hash']).decode()
        data['merkle_root'] = binascii.hexlify(data['merkle_root']).decode()
        data['hash'] = binascii.hexlify(data['hash']).decode()
    verify_pow(h, blockhash)
    return data


def verify_pow(header, blockhash):
    bits = header[72:76][::-1]
    target = int.from_bytes(bits[1:], 'big') * 2 ** (8 * (bits[0] - 3))
    if target < int.from_bytes(blockhash, 'little'):
        return True
    raise exceptions.InvalidPOWException


def serialize_header(inp):
    o = encode(inp['version'], 256, 4)[::-1] + \
        binascii.unhexlify(inp['prev_block_hash'])[::-1] + \
        binascii.unhexlify(inp['merkle_root'])[::-1] + \
        encode(inp['timestamp'], 256, 4)[::-1] + \
        encode(inp['bits'], 256, 4)[::-1] + \
        encode(inp['nonce'], 256, 4)[::-1]
    h = binascii.hexlify(bin_sha256(bin_sha256(o))[::-1]).decode()
    if inp.get('hash'):
        assert h == inp['hash'], (hashlib.sha256(o), inp['hash'])
    return binascii.hexlify(o).decode()


def get_nearest_parent(number: int, divisor: int):
    return int(number - number % divisor)


async def async_delayed_task(task, seconds: int=0, disable_log=True):
    from spruned.application.logging_factory import Logger
    not disable_log and Logger.root.debug('Scheduling task %s in %s seconds', task, seconds)
    await asyncio.sleep(seconds)
    return await task


def create_directory(ctx, storage_address):  # pragma: no cover
    import os
    if not os.path.exists(ctx.datadir):
        os.makedirs(ctx.datadir)
    if not os.path.exists(storage_address):
        os.makedirs(storage_address)


_last_internet_connection_check = None


async def check_internet_connection():  # pragma: no cover
    global _last_internet_connection_check
    if _last_internet_connection_check and int(time.time()) - _last_internet_connection_check < 30:
        return True

    from spruned.application.context import ctx
    from spruned.application.logging_factory import Logger
    from spruned.settings import CHECK_NETWORK_HOST
    import asyncio
    import subprocess
    import os
    if not ctx.proxy:
        Logger.root.debug('Checking internet connectivity')
        i = 0
        while i < 10:
            import random
            host = random.choice(CHECK_NETWORK_HOST)
            ret_code = subprocess.call(['ping', '-c', '1', '-W', '5', host],
                                       stdout=open(os.devnull, 'w'),
                                       stderr=open(os.devnull, 'w'))
            if not ret_code:
                _last_internet_connection_check = int(time.time())
                return True
            i += 1
        Logger.root.debug('No internet connectivity!')
    else:
        host, port = ctx.proxy.split(':')
        Logger.root.debug('Checking proxy connectivity')
        try:
            _last_internet_connection_check = int(time.time())
            p, t = await asyncio.open_connection(host=host, port=port)
            t.close()
            return True
        except Exception:
                Logger.root.debug('Cannot connect to proxy %s:%s', host, port, exc_info=True)
    return False


def script_to_scripthash(script):
    # This code comes from the Electrum codebase.
    h = hashlib.sha256(bytes.fromhex(script)).digest()[0:32]
    return binascii.hexlify(bytes(reversed(h))).decode('ascii')


class ElectrumMerkleVerify:
    # This is a microfork of Electrum Merkle Verify modules. Come from the Electrum codebase
    # it comes from var modules into
    # https://github.com/spesmilo/electrum/tree/81666bf9ac8b42d0ac25415ee3815d899c8adda6/lib
    # Thanks to the Electrum team.

    hash_decode = lambda x: bytes.fromhex(x)[::-1]

    @staticmethod
    def to_bytes(something, encoding='utf8'):
        """
        cast string to bytes() like object, but for python2 support it's bytearray copy
        """
        if isinstance(something, bytes):
            return something
        if isinstance(something, str):
            return something.encode(encoding)
        elif isinstance(something, bytearray):
            return bytes(something)
        else:
            raise TypeError("Not a string or bytes like object")

    @classmethod
    def sha256(cls, x):
        x = cls.to_bytes(x, 'utf8')
        return bytes(hashlib.sha256(x).digest())

    @classmethod
    def _hash(cls, x):
        x = cls.to_bytes(x, 'utf8')
        out = bytes(cls.sha256(cls.sha256(x)))
        return out

    @classmethod
    def hash_merkle_root(cls, merkle_s, target_hash, pos):
        h = bytes.fromhex(target_hash)[::-1]
        for i in range(len(merkle_s)):
            item = merkle_s[i]
            h = cls._hash(cls.hash_decode(item) + h) if ((pos >> i) & 1) else cls._hash(h + cls.hash_decode(item))
        return binascii.hexlify(h[::-1]).decode()

    @classmethod
    def verify_merkle(self, txid, merkle, header):
        if not header or merkle.get('merkle', None) is None:
            return
        merkle_root = self.hash_merkle_root(merkle['merkle'], txid, merkle['pos'])
        expected = (header.get('merkle_root') and binascii.hexlify(header['merkle_root']).decode())
        return merkle_root == expected


def is_address(addr, prefix):
    ADDR_RE = re.compile("^[%s][a-km-zA-HJ-NP-Z0-9]{26,33}$" % prefix)
    return bool(ADDR_RE.match(addr))
