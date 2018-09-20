import abc
from typing import List


class ConnectionAbstract(metaclass=abc.ABCMeta):  # pragma: no cover

    @property
    @abc.abstractmethod
    def start_score(self):
        pass

    @property
    @abc.abstractmethod
    def hostname(self):
        pass

    @property
    @abc.abstractmethod
    def score(self):
        pass

    @property
    @abc.abstractmethod
    def version(self):
        pass

    @property
    @abc.abstractmethod
    def connected(self):
        pass

    @property
    @abc.abstractmethod
    def last_header(self):
        pass

    @abc.abstractmethod
    def is_online(self) -> bool:
        pass

    @abc.abstractmethod
    def add_on_header_callbacks(self, callback):
        pass

    @abc.abstractmethod
    def add_on_connect_callback(self, callback):
        pass

    @abc.abstractmethod
    def add_on_disconnect_callback(self, callback):
        pass

    @abc.abstractmethod
    def add_on_peers_callback(self, callback):
        pass

    @abc.abstractmethod
    def connect(self):
        pass

    @abc.abstractmethod
    def ping(self, timeout=None):
        pass

    @property
    @abc.abstractmethod
    def errors(self):
        pass

    @abc.abstractmethod
    def disconnect(self):
        pass

    @abc.abstractmethod
    def add_error(self, *a):
        pass

    @abc.abstractmethod
    def add_success(self):
        pass


class ConnectionPoolAbstract(metaclass=abc.ABCMeta):  # pragma: no cover
    @property
    @abc.abstractmethod
    def established_connections(self) -> List:
        pass

    @property
    @abc.abstractmethod
    def connections(self) -> List:
        pass

    @abc.abstractmethod
    def add_on_connected_observer(self, observer):
        pass

    @abc.abstractmethod
    def add_header_observer(self, observer):
        pass

    @abc.abstractmethod
    async def connect(self):
        pass

    @abc.abstractmethod
    def is_online(self) -> bool:
        pass
