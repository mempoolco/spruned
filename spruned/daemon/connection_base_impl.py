import abc
import asyncio
import time
from typing import Dict, List
from spruned.application.tools import async_delayed_task
from spruned.daemon.abstracts import ConnectionAbstract


class BaseConnection(ConnectionAbstract, metaclass=abc.ABCMeta):
    def __init__(
            self, hostname: str, proxy=False, loop=None,
            start_score=10, timeout=10, expire_errors_after=180,
            is_online_checker: callable=None, delayer=async_delayed_task
    ):
        self._is_online_checker = is_online_checker
        self._hostname = hostname
        self._hostname = hostname
        self._proxy = proxy
        self._version = None
        self.connected_at = None
        self._on_headers_callbacks = []
        self._on_connect_callbacks = []
        self._on_disconnect_callbacks = []
        self._on_errors_callbacks = []
        self._on_peers_callbacks = []
        self.loop = loop or asyncio.get_event_loop()
        self._start_score = start_score
        self._score = 0
        self._last_header = None
        self._subscriptions = []
        self._timeout = timeout
        self._errors = []
        self._peers = []
        self._expire_errors_after = expire_errors_after
        self._is_online_checker = is_online_checker
        self.delayer = delayer

    @property
    def proxy(self):
        return self._proxy

    @property
    def hostname(self):
        return self._hostname

    def add_error(self, *a):
        if len(a) and isinstance(a[0], int):
            self._errors.append(a[0])
        else:
            self._errors.append(int(time.time()))

    def add_success(self):
        self._score += 1

    def is_online(self):
        if self._is_online_checker is not None:
            return self._is_online_checker()
        return True

    def add_on_header_callbacks(self, callback):
        self._on_headers_callbacks.append(callback)

    def add_on_connect_callback(self, callback):
        self._on_connect_callbacks.append(callback)

    def add_on_disconnect_callback(self, callback):
        self._on_disconnect_callbacks.append(callback)

    def add_on_peers_callback(self, callback):
        self._on_peers_callbacks.append(callback)

    def add_on_error_callback(self, callback):
        self._on_errors_callbacks.append(callback)

    async def on_header(self, header):
        self._last_header = header
        for callback in self._on_headers_callbacks:
            self.loop.create_task(callback(self))

    async def on_connect(self):
        for callback in self._on_connect_callbacks:
            self.loop.create_task(callback(self))

    async def on_error(self, error):
        if not self.is_online:
            return
        self.add_error()
        for callback in self._on_errors_callbacks:
            self.loop.create_task(callback(self, error_type=error))

    async def on_peers(self):
        for callback in self._on_peers_callbacks:
            self.loop.create_task(callback(self))

    @property
    def start_score(self):
        return self._start_score

    @property
    def version(self):
        return self._version

    @property
    def last_header(self) -> Dict:
        return self._last_header

    @property
    def subscriptions(self) -> List:
        return self._subscriptions

    @property
    def score(self):
        return self._start_score - len(self.errors)

    @property
    def errors(self):
        now = int(time.time())
        self._errors = [error for error in self._errors if now - error < self._expire_errors_after]
        return self._errors

    @property
    def peers(self):
        return self._peers
