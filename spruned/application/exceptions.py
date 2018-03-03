class SprunedException(Exception):
    pass


class ServiceException(SprunedException):
    pass


class HTTPClientException(SprunedException):
    pass