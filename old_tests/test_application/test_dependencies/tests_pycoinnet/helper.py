import hashlib

from pycoin import ecdsa
from pycoin.block import Block
from pycoin.encoding.sec import public_pair_to_sec

from pycoin.key.Key import Key
from pycoin.merkle import merkle
from pycoin.tx.Tx import Tx, TxIn, TxOut


GENESIS_TIME = 1390000000
DEFAULT_DIFFICULTY = 3000000
HASH_INITIAL_BLOCK = b'\0' * 32


def make_hash(i, s=b''):
    return hashlib.sha256(("%d_%s" % (i, s)).encode()).digest()


def make_tx(i):
    key = Key(12345 * (i+29))
    script = standard_tx_out_script(key.address())
    txs_in = [TxIn(make_hash(i*10000+idx), (i+idx) % 2) for idx in range(3)]
    txs_out = [TxOut(i*40000, script) for idx in range(2)]
    tx = Tx(1, txs_in, txs_out)
    return tx


def make_headers(count, header=None):
    if header is None:
        last_hash = HASH_INITIAL_BLOCK
    else:
        last_hash = header.hash()
    tweak = last_hash
    headers = []
    for i in range(count):
        headers.append(
            Block(version=1, previous_block_hash=last_hash, merkle_root=make_hash(i, tweak),
                  timestamp=GENESIS_TIME+i*600, difficulty=DEFAULT_DIFFICULTY, nonce=i*137))
        last_hash = headers[-1].hash()
    return headers


def coinbase_tx(secret_exponent):
    public_pair = ecdsa.public_pair_for_secret_exponent(
        ecdsa.secp256k1.generator_secp256k1, secret_exponent)
    public_key_sec = public_pair_to_sec(public_pair)
    return Tx.coinbase_tx(public_key_sec, 2500000000)


def make_blocks(count, nonce_base=30000, previous_block_hash=HASH_INITIAL_BLOCK):
    blocks = []
    for i in range(count):
        s = i * nonce_base
        txs = [coinbase_tx(i+1)] + [make_tx(i) for i in range(s, s+8)]
        nonce = s
        while True:
            merkle_root = merkle([tx.hash() for tx in txs])
            block = Block(version=1, previous_block_hash=previous_block_hash, merkle_root=merkle_root,
                          timestamp=GENESIS_TIME+i*600, difficulty=i, nonce=nonce)
            block.set_txs(txs)
            if block.hash()[-1] == i & 0xff:
                break
            nonce += 1
        blocks.append(block)
        previous_block_hash = block.hash()
    return blocks
