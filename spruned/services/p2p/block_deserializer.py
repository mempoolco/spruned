import logging
from pycoin.block import Block


class BlockDeserializer:
    def __init__(self):
        self.total_entries = 0

    def parse_tx_in(self, i):
        self.total_entries += 1
        return {
            'hash': i.previous_hash != b'\0' * 32 and bytes.fromhex(str(i.previous_hash)) or None,
            'index': None if i.previous_index == 4294967295 else int(i.previous_index).to_bytes(4, 'little'),
            'script': i.script,
            'witness': i.witness
        }

    def parse_tx_out(self, o):
        self.total_entries += 1
        return {
            'script': o.script,
            'amount': o.coin_value.to_bytes(8, 'little')
        }

    def parse_tx(self, t):
        return {
            'hash': bytes.fromhex(str(t.hash())),
            'bytes': t.as_bin(),
            'ins': tuple(map(self.parse_tx_in, t.txs_in)),
            'outs': tuple(map(self.parse_tx_out, t.txs_out)),
            'gen': bool(t.is_coinbase())
        }

    @classmethod
    def deserialize_block(cls, data):
        """
        to be run into multiprocessing constraints.
        use built-in serializable types.
        """
        self = cls()
        try:
            block = Block.from_bin(data)
            header = block.as_blockheader()
            data = {
                'success': True,
                'data': {
                    'header': header.as_bin(),
                    'merkle_root': bytes.fromhex(str(header.merkle_root)),
                    'size': len(block.as_bin()),
                    'hash': bytes.fromhex(str(header.hash())),
                    'txs': tuple(map(self.parse_tx, block.txs)),
                    'total_entries': self.total_entries
                }
            }
        except Exception as e:
            logging.getLogger('root').exception('Exception deserializing block')
            data = {'success': False, 'error': str(e)}
        return data
