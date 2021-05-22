from spruned.application.exceptions import SprunedException, RetryException


class ConfigurationException(SprunedException):
    pass


class HeadersInconsistencyException(SprunedException):
    pass


class NoQuorumOnResponsesException(SprunedException):
    pass


class ConsistencyCheckRetryException(SprunedException):
    pass


class NoPeersException(SprunedException):
    pass


class NetworkHeadersInconsistencyException(SprunedException):
    pass


class NoHeadersException(SprunedException):
    pass


class ElectrumMissingResponseException(SprunedException):
    pass


class MissingResponseException(SprunedException):
    pass


class NoServersException(SprunedException):
    pass


class BlocksInconsistencyException(SprunedException):
    pass


class GenesisTransactionRequestedException(SprunedException):
    pass


class PeerBlockchainBehindException(SprunedException):
    pass


class PeerVersionMismatchException(SprunedException):
    pass


class BrokenDataException(SprunedException):
    pass


class BootstrapException(SprunedException):
    pass


class NoConnectionsAvailableException(RetryException):
    pass


class MissingPeerResponseException(RetryException):
    pass


class PeerHandshakeException(SprunedException):
    pass
