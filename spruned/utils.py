import asyncio
import functools

import typing

from spruned.application import exceptions

_exc_type = typing.Union[
    typing.Tuple,
    typing.Type[exceptions.RetryException]
]


def async_retry(retries: int, wait: float, on_exception: _exc_type):
    i = 0

    def decorator(f):
        @functools.wraps(f)
        async def _function(*a, **kw):
            if kw.get('retry', None) is not None:
                kw['retry'] += 1
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
                    raise
        return _function
    return decorator

