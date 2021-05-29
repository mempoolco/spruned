import logging
from pycoin.block import Block


def parse_tx_in(i):
    return {
        'hash': i.previous_hash != b'\0' * 32 and i.previous_hash or None,
        'index': i.previous_index != 4294967295 and i.previous_index or None,
        'script': i.script,
        'witness': i.witness
    }


def parse_tx_out(o):
    return {
        'script': o.script,
        'amount': o.coin_value
    }


def parse_tx(t):
    return {
        'hash': bytes.fromhex(str(t.hash())),
        'bytes': t.as_bin(),
        'ins': tuple(map(parse_tx_in, t.txs_in)),
        'outs': tuple(map(parse_tx_out, t.txs_out)),
        'gen': bool(t.is_coinbase())
    }


def deserialize_block(data):
    """
    to be run into multiprocessing constraints.
    use built-in serializable types.
    """
    try:
        block = Block.from_bin(data)
        header = block.as_blockheader()
        data = {
            'success': True,
            'data': {
                'header': header.as_bin(),
                'size': len(block.as_bin()),
                'hash': bytes.fromhex(str(header.hash())),
                'txs': tuple(
                    map(
                        parse_tx,
                        block.txs
                    )
                )
            }
        }
    except Exception as e:
        logging.getLogger('root').exception('Exception deserializing block')
        data = {
            'success': False,
            'error': str(e)
        }
    return data
