import asyncio
import functools

import typing

from spruned.application import exceptions


def async_retry(retries: int, wait: float, on_exception: typing.Type[exceptions.SprunedException]):
    i = 0

    def decorator(f):
        @functools.wraps(f)
        async def _function(*a, **kw):
            while 1:
                try:
                    return await f(*a, **kw)
                except on_exception as e:
                    nonlocal i
                    i += 1
                    if i <= retries:
                        await asyncio.sleep(wait)
                    elif getattr(e, 'fail_silent', False):
                        return
                    else:
                        raise
        return _function
    return decorator
