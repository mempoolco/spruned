import multiprocessing
import time
import typing
from copy import copy


def _validate_utxo(cache, vin, block_height):
    pass


def _spend_utxo(cache, vin, block_height):
    if block_height < cache['min_safe_height']:
        if not _validate_utxo(cache, vin, block_height):
            return [False, vin]
        return [True, vin]


def _add_utxo(cache, vout, tx, i, height_in_bytes, is_coinbase):
    return 44


def process_block(
        block: typing.Dict,
        cache: multiprocessing.Manager
):
    """
    to be used into a multiprocessing pool.
    """
    height_in_bytes = block['height'].to_bytes(4, 'little')
    failed = copy(cache['failed_blocks'].get(block['height'], {}))
    for vin_coord, entry in failed.items():
        vin = entry[0]
        outcome = _spend_utxo(
            cache, vin, block['height']
        )
        if outcome[0]:
            cache['-utxo'].append(outcome[1])
            cache['failed_blocks'][block['height']].pop(vin_coord)

    if cache['failed_blocks'].get(block['height']) and min(cache['processing_blocks']) < block['height']:
        time.sleep(0.01)
        return process_block(block, cache)

    elif cache['failed_blocks'].get(block['height']):
        cache['invalid_blocks'].append([block['hash'], block['height']])
        return False

    for tx in block['txs']:
        if not tx['gen']:
            for i, vin in tx['ins']:
                vin_coord = tx['hash'] + i.to_bytes(4, 'little')
                if vin_coord not in cache['del_utxo'] and \
                        vin_coord not in cache['failed_blocks'].get(block['height'], {}):

                    outcome = _spend_utxo(
                        cache, vin, block['height']
                    )
                    if outcome[0]:
                        cache['-utxo'][[outcome[1]['vin_coord']]] = outcome[1]['rev_state']
                    else:
                        cache['failed_blocks'].setdefault(block['height'], dict())
                        cache['failed_blocks'][block['height']][vin_coord] = outcome[1]
                        cache['missing_utxo'].append(vin_coord)  # request for missing utxo on the main process

        for i, vout in enumerate(tx['outs']):
            outpoint = tx['hash'] + i.to_bytes(4, 'little')
            if outpoint not in cache['+utxo']:
                cache['+utxo'][outpoint] = _add_utxo(cache, vout, tx, i, height_in_bytes, tx['gen'])

    if cache['failed_blocks'].get(block['height']) and min(cache['processing_blocks']) < block['height']:
        time.sleep(0.01)
        return process_block(block, cache)

    elif cache['failed_blocks'][block['height']]:
        cache['invalid_blocks'].append([block['hash'], block['height']])
        return False

    cache['processing_blocks'].pop(block['height'])
    return True
