class SprunedException(Exception):
    def __init_(self, *a, **kw):
        super(SprunedException).__init__(*a)


class ServiceException(SprunedException):
    pass


class HTTPClientException(SprunedException):
    pass


class SpentTxOutException(SprunedException):
    pass


class InvalidPOWException(SprunedException):
    pass


class SourcesDisagreementException(SprunedException):
    pass


class MempoolDisabledException(SprunedException):
    pass


class ItemNotFoundException(SprunedException):
    pass


class StorageErrorException(SprunedException):
    pass


class InvalidHeaderException(SprunedException):
    pass


class RetryException(SprunedException):
    def __init__(self, *a, fail_silent=False, **kw):
        super(RetryException).__init__(*a)
        self.fail_silent = fail_silent


class ConsensusNotReachedException(SprunedException):
    pass


class DatabaseInconsistencyException(SprunedException):
    pass
