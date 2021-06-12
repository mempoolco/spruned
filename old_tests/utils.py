async def async_coro(response):
    return response


class MockValidator(object):

    def __init__(self, validator):
        # validator is a function that takes a single argument and returns a bool.
        self.validator = validator

    def __eq__(self, other):
        return bool(self.validator(other))


def coro_call(coro_name: str):
    def test_coro(coro):
        return coro.cr_code.co_name == coro_name

    return MockValidator(test_coro)


def in_range(n1: int, n2: int):
    def test(n):
        return n1 <= n <= n2
    return MockValidator(test)


def make_headers(s: int, e: int, prevblock_0: str= None, with_timestamp=True):
    import os
    import binascii
    _headers = []
    for i, x in enumerate(range(s, e)):
        block_hash = binascii.hexlify(os.urandom(32)).decode()
        _headers.append({
            'block_hash': block_hash,
            'prev_block_hash': x != 0 and (_headers[i-1]['block_hash'] if i > 0 else prevblock_0),
            'timestamp': 1,
            'header_bytes': os.urandom(80),
            'block_height': x
        }
        )
        if x == 0:
            _headers[0].pop('prev_block_hash')
        if not with_timestamp:
            _headers[i].pop('timestamp')
    return _headers


def batcher_factory(self):
    class FakeBatcher:
        @staticmethod
        async def add_peer(data):
            nonlocal self
            return self.batcher_factory.add_peer(data)

        @staticmethod
        async def inv_item_to_future(data):
            nonlocal self
            return async_coro(self.batcher_factory.inv_item_to_future(data))

    return FakeBatcher()
