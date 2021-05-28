from typing import Any

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


def reach_consensus_on_value(*value: Any, agreement=0.9) -> str:
    """
    ensure 90% of peers agree
    """
    scores = score_values(*value)
    if scores[0]['count'] < len(value) * agreement:
        raise exceptions.ConsensusNotReachedException('Insufficient score: %s', scores[0]['count'] / len(value))
    return scores[0]['value']
