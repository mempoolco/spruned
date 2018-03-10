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
