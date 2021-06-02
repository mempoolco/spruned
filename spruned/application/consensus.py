import hashlib
import typing

from spruned.application import exceptions


def verify_pow(header: bytes, blockhash: bytes):
    bits = header[72:76][::-1]
    target = int.from_bytes(bits[1:], 'big') * 2 ** (8 * (bits[0] - 3))
    if target < int.from_bytes(blockhash, 'little'):
        return True
    raise exceptions.InvalidPOWException


def score_values(*value):
    unique = set(value)
    scores = sorted(
        map(
            lambda val: {
                'value': val,
                'count': value.count(val)
            },
            unique
        ),
        key=lambda x: x['count'], reverse=True
    )
    return scores


def reach_consensus_on_value(*value: typing.Any, agreement=0.9) -> str:
    """
    ensure 90% of peers agree
    """
    scores = score_values(*value)
    if scores[0]['count'] < len(value) * agreement:
        raise exceptions.ConsensusNotReachedException('Insufficient score: %s', scores[0]['count'] / len(value))
    return scores[0]['value']


def _dbl_sha_256(tx_hash_1: bytes, tx_hash_2: bytes):
    _hashes = tx_hash_1[::-1] + tx_hash_2[::-1]
    return hashlib.sha256(hashlib.sha256(_hashes).digest()).digest()[::-1]


def get_merkle_root(transaction_ids: typing.List[bytes]):
    if len(transaction_ids) == 1:
        return transaction_ids[0]
    _hashes = []
    for i in range(0, len(transaction_ids) - 1, 2):
        _hashes.append(
            _dbl_sha_256(transaction_ids[i], transaction_ids[i + 1])
        )
    if len(transaction_ids) % 2 == 1:
        _hashes.append(
            _dbl_sha_256(transaction_ids[-1], transaction_ids[-1])
        )
    return get_merkle_root(_hashes)
