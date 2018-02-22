import queue
import threading
import time
from spruned.service.abstract import RPCAPIService
from spruned.service.connectrum_client import ConnectrumClient


class ConnectrumService(RPCAPIService):
    def __init__(self, coin):
        assert coin.value == 1
        self.coin = coin
        self._keepalive = True
        self._cmd_queue = None  # type: queue.Queue
        self._res_queue = None  # type: queue.Queue
        self._status_queue = None  # type: queue.Queue
        self._client = None
        self._thread = None

    def disconnect(self):
        self._call({'cmd': 'die'})
        start = int(time.time())
        while not self._thread.is_alive():
            if int(time.time()) > start + 5:
                raise ConnectionResetError('Error disconnecting from Electrum Network')
        return True

    def connect(self, loop=None, concurrency=1, max_retries_on_discordancy=3, connections_concurrency_ratio=3):
        if not self._client:
            self._cmd_queue = queue.Queue(maxsize=1)
            self._res_queue = queue.Queue(maxsize=1)
            self._status_queue = queue.Queue(maxsize=1)

            self._client = ConnectrumClient(
                self.coin,
                loop,
                concurrency=concurrency,
                max_retries_on_discordancy=max_retries_on_discordancy,
                connections_concurrency_ratio=connections_concurrency_ratio
            )
            self._thread = threading.Thread(
                target=self._client.loop.run_until_complete, args=[
                    self._client.connect(
                        self._cmd_queue,
                        self._res_queue,
                        self._status_queue
                    )
                ]
            )
            self._thread.start()
            return True

    def _call(self, payload):
        self._cmd_queue.put(payload, timeout=2)
        try:
            response = self._res_queue.get(timeout=5)
        except queue.Empty:
            return
        if response.get('error'):
            return
        return response

    def _get_address_history(self, address):
        payload = {
            'cmd': 'getaddresshistory',
            'args': [address]
        }
        response = self._call(payload)
        return response

    def _get_block_header(self, height: int):
        payload = {
            'cmd': 'getblockheader',
            'args': [height]
        }
        response = self._call(payload)
        return response

    def getrawtransaction(self, txid: str, **_):
        payload = {
            'cmd': 'getrawtransaction',
            'args': [txid]
        }
        response = self._call(payload)
        return response and {
            'rawtx': response['response'],
            'txid': txid,
            'source': 'electrum'
        }

    def getblock(self, _):
        return

    @property
    def status(self):
        try:
            res = self._status_queue.get(timeout=0.2)
            self._status_queue.put(res)
            return res
        except queue.Empty:
            return

    def is_connected(self) -> bool:
        return 'c' in self.status

    @property
    def connections(self):
        try:
            status = self.status
            if 'c' in status or 'p' in status:
                x, y = status.split(',')
                return int(y.strip())
        except queue.Empty:
            return 0
        return 0

    @property
    def available(self):
        return self.is_connected()
