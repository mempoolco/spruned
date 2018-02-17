from bitcoin import deserialize, serialize


def purge_from_empty_segwit(tx):
    tx = deserialize(tx)
    tx['segwit'] = True
    for i, vin in enumerate(tx['ins']):
        if vin.get('txinwitness', '0'*64) == '0'*64:
            tx['ins'][i]['txinwitness'] = ''
    return serialize(tx)
