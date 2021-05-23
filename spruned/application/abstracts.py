import abc
import time
from spruned.application import exceptions
from spruned.application.logging_factory import Logger


class RPCAPIService(metaclass=abc.ABCMeta):
    errors_ttl = 5
    max_errors_before_downtime = 1
    errors = []
    client = None
    throttling_error_codes = []

    @abc.abstractmethod
    def getrawtransaction(self, txid, **kwargs):
        pass  # pragma: no cover

    def _increase_errors(self):
        now = int(time.time())
        self.errors.append(now)

    @property
    def available(self):
        now = int(time.time())
        _errors = []
        for error in self.errors:
            if error > now - self.errors_ttl:
                _errors.append(error)
        self.errors = _errors
        return bool(len(self.errors) < self.max_errors_before_downtime)

    async def get(self, path):
        try:
            return await self.client.get(path)
        except exceptions.HTTPClientException as e:
            from aiohttp import ClientResponseError
            cause = e.__cause__
            if isinstance(cause, ClientResponseError):
                if cause.status in self.throttling_error_codes:
                    Logger.third_party.warning('throttling %s' % self.__class__.__name__)
                else:
                    Logger.third_party.exception('Error on %s: %s' % (self.__class__.__name__, e.__cause__))
                self._increase_errors()
