import logging
from pycoin.block import Block


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
                'txs': list(
                    map(
                        lambda t: {
                            'hash': bytes.fromhex(str(t.hash())),
                            'bytes': t.as_bin()
                        },
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
