from spruned.application.exceptions import SprunedException


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


class ElectrodMissingResponseException(SprunedException):
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