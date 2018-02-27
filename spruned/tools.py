import hashlib
import binascii
from bitcoin import deserialize, serialize, decode, bin_sha256


def normalize_transaction(tx):
    _tx = deserialize(tx)
    _tx['segwit'] = True
    for i, vin in enumerate(_tx['ins']):
        if vin.get('txinwitness', '0'*64) == '0'*64:
            _tx['ins'][i]['txinwitness'] = ''
    return serialize(_tx)


def blockheader_to_blockhash(header: (bytes, str)) -> (bytes, str):
    if isinstance(header, bytes):
        h, fmt = header, 'bin'
    else:
        h, fmt = binascii.unhexlify(header.encode()), 'hex'
    blockhash = hashlib.sha256(hashlib.sha256(h).digest())
    bytes_blockhash = blockhash.digest()[::-1]
    return fmt == 'hex' and binascii.hexlify(bytes_blockhash).decode() or bytes_blockhash


def deserialize_header(header):
    if isinstance(header, bytes):
        h, fmt = header, 'bin'
    else:
        h, fmt = binascii.unhexlify(header.encode()), 'hex'
    data = {
        "version": decode(h[:4][::-1], 256),
        "prevhash": h[4:36][::-1],
        "merkle_root": h[36:68][::-1],
        "timestamp": decode(h[68:72][::-1], 256),
        "bits": decode(h[72:76][::-1], 256),
        "nonce": decode(h[76:80][::-1], 256),
        "hash": bin_sha256(bin_sha256(h))[::-1]
    }
    if fmt == 'hex':
        data['prevhash'] = binascii.hexlify(data['prevhash']).decode()
        data['merkle_root'] = binascii.hexlify(data['merkle_root']).decode()
        data['hash'] = binascii.hexlify(data['hash']).decode()
    return data
