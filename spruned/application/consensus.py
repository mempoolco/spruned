from spruned.application import exceptions


def verify_pow(header: bytes, blockhash: bytes):
    bits = header[72:76][::-1]
    target = int.from_bytes(bits[1:], 'big') * 2 ** (8 * (bits[0] - 3))
    if target < int.from_bytes(blockhash, 'little'):
        return True
    raise exceptions.InvalidPOWException


def reach_consensus_on_blockhash(*blockhash: str) -> str:
    assert len(blockhash) > 5
    unique = set(blockhash)
    scores = sorted(
        map(
            lambda b: {
                'h': b,
                'c': blockhash.count(b)
            },
            unique
        ),
        key=lambda x: x['c'], reverse=True
    )
    if scores[0]['c'] < len(blockhash) * .8:
        raise exceptions.ConsensusNotReachedException('Insufficient score: %s', scores[0]['c'] / len(blockhash))
    return scores[0]['h']
