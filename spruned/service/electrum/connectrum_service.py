import queue
import threading
import time
from spruned.service.abstract import RPCAPIService
import retrying
from spruned.logging_factory import Logger


class ConnectrumService(RPCAPIService):
    def __init__(self, coin, reactor):
        assert coin.value == 1
        self.coin = coin
        self._keepalive = True
        self._cmd_queue = queue.Queue(maxsize=1)
        self._res_queue = queue.Queue(maxsize=1)
        self._status_queue = queue.Queue(maxsize=1)
        self._client_instance = None
        self._thread = None
        self._reactor = reactor

    def disconnect(self):
        Logger.electrum.debug('ConnectrumService - disconnecting Connectrum')
        self._call({'cmd': 'die'})
        start = int(time.time())
        while not self._thread.is_alive():
            if int(time.time()) > start + 5:
                raise ConnectionResetError('Error disconnecting from Electrum Network')
        Logger.electrum.debug('ConnectrumService - disconnected Connetrum')
        return True

    def connect(self):
        Logger.electrum.debug('ConnectrumService - connect, spawn Connectrum Thread')
        if not self._client_instance:
            self._client_instance = self._reactor
            self._thread = threading.Thread(
                target=self._client_instance.loop.run_until_complete, args=[
                    self._client_instance.start(
                        self._cmd_queue,
                        self._res_queue,
                        self._status_queue,
                    )
                ],
            )
            self._thread.start()
            return True

    @retrying.retry(wait_fixed=100, retry_on_exception=lambda e: isinstance(e, queue.Full), stop_max_attempt_number=25)
    def _call(self, payload):
        """
        25 retries * 0.1+0.1, max 5 seconds then we fail on full queue
        """
        Logger.electrum.debug('ConnectrumService - call, payload: %s', payload)
        self._cmd_queue.put(payload, timeout=0.1)
        try:
            response = self._res_queue.get(timeout=5)
            Logger.electrum.debug('ConnectrumService - call, response: %s', response)
        except queue.Empty:
            return
        except queue.Full:
            Logger.electrum.warning('ConnectrumService - queue Full, retrying')
            raise
        if response.get('error'):
            Logger.electrum.error('ConnectrumService - call error - response: %s', response)
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
