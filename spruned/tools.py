from bitcoin import deserialize, serialize


def normalize_transaction(tx):
    _tx = deserialize(tx)
    _tx['segwit'] = True
    for i, vin in enumerate(_tx['ins']):
        if vin.get('txinwitness', '0'*64) == '0'*64:
            _tx['ins'][i]['txinwitness'] = ''
    return serialize(_tx)