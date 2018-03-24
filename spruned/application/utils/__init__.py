def split(data, offset):
    return [
        data[i:i+offset] for i in range(0, len(data), offset)
    ]
