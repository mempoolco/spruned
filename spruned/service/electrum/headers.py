import asyncio
import time

from spruned.logging_factory import Logger
from spruned.service.electrum.connectrum_client import ConnectrumClient


class HeadersRepository():
    def __init__(self, connectrumclient, bestheader_ttl=30):
        self._bestheader_ttl = bestheader_ttl
        self._connectrum : ConnectrumClient = connectrumclient
        self._best_height = {'time': 0, 'value': 0}

    @staticmethod
    def _height_to_chunks_index(height):
        return height // 2016

    @property
    def best_local_header(self):
        return 0

    @property
    def best_network_height(self):
        if self._best_height['time'] and int(time.time()) - self._best_height['time'] < self._bestheader_ttl:
            return self._best_height['value']
        return None

    async def _get_best_header(self):
        Logger.electrum.warning('GET BEST HEADER INVOKED')
        responses = []
        futures = [
            peer.RPC('blockchain.headers.subscribe') for peer in self._connectrum._pick_peers()
        ]
        for response in await asyncio.gather(*futures):
            response and responses.append(response)
        return responses

    async def _get_missing_chunk(self):
        chunk_index = self._height_to_chunks_index(self.best_height)

    @property
    def aligned(self):
        if self.best_network_height and self.best_network_height == self.best_local_header:
            return True

    async def align(self):
        while not self.aligned:
            
            headers_chunk = await self._get_missing_chunk()
            self._save_headers_chunk(headers_chunk)
        return self.best_height
