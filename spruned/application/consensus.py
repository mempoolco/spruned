from spruned.application import exceptions


def verify_pow(header: bytes, blockhash: bytes):
    bits = header[72:76][::-1]
    target = int.from_bytes(bits[1:], 'big') * 2 ** (8 * (bits[0] - 3))
    if target < int.from_bytes(blockhash, 'little'):
        return True
    raise exceptions.InvalidPOWException


def reach_consensus_on_blockhash(*blockhash: str) -> str:
    """
    ensure 90% of peers agree
    """
    unique = set(blockhash)
    scores = sorted(
        map(
            lambda b: {
                'hash': b,
                'count': blockhash.count(b)
            },
            unique
        ),
        key=lambda x: x['count'], reverse=True
    )
    if scores[0]['count'] < len(blockhash) * 0.9:
        raise exceptions.ConsensusNotReachedException('Insufficient score: %s', scores[0]['count'] / len(blockhash))
    return scores[0]['hash']
