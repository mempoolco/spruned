import asyncio
import binascii
from typing import Dict
from spruned.application.context import ctx
from spruned.application.exceptions import InvalidPOWException
from spruned.application.logging_factory import Logger
from spruned.daemon import exceptions
from spruned.application.tools import blockheader_to_blockhash, deserialize_header, serialize_header
from spruned.daemon.electrod.electrod_connection import ElectrodConnectionPool, ElectrodConnection


class ElectrodInterface:
    def __init__(self, connectionpool: ElectrodConnectionPool, loop=asyncio.get_event_loop()):
        self._network = ctx.get_network()
        self.pool = connectionpool
        self._checkpoints = self._network['checkpoints']
        self.loop = loop

    @property
    def is_pool_online(self):  # pragma: no cover
        return self.pool.is_online()

    def _parse_header(self, electrum_header: Dict):
        header_hex = serialize_header(electrum_header)
        blockhash_from_header = blockheader_to_blockhash(header_hex)
        if electrum_header['block_height'] in self._checkpoints:
            if self._checkpoints[electrum_header['block_height']] != blockhash_from_header:
                raise exceptions.NetworkHeadersInconsistencyException

        header_data = deserialize_header(header_hex)
        return {
            'block_hash': blockhash_from_header,
            'block_height': electrum_header['block_height'],
            'header_bytes': binascii.unhexlify(header_hex),
            'prev_block_hash': header_data['prev_block_hash'],
            'timestamp': header_data['timestamp']
        }

    def add_header_subscribe_callback(self, callback):
        async def parse_and_go(peer, res):
            try:
                header = self._parse_header(res)
                return await callback(peer, header)
            except InvalidPOWException:
                Logger.electrum.error('Wrong POW for header %s from peer %s. Banning', res, peer)
                self.loop.create_task(peer.disconnect())
        self.pool.add_header_observer(parse_and_go)

    def add_on_connected_callback(self, callback):
        self.pool.add_on_connected_observer(callback)

    async def get_header(self, height: int, fail_silent_out_of_range=False, get_peer=False):
        try:
            response = await self.pool.call(
                'blockchain.block.get_header', height, get_peer=True
            )
            peer, header = response
        except exceptions.ElectrodMissingResponseException:
            if fail_silent_out_of_range:
                return
            raise
        try:
            parsed_header = self._parse_header(header)
        except (exceptions.NetworkHeadersInconsistencyException, InvalidPOWException):
            Logger.electrum.error('Wrong POW for header %s from peer %s. Banning', header, peer)
            self.loop.create_task(peer.disconnect())
            return

        if not get_peer:
            return parsed_header
        return peer, parsed_header

    async def handle_peer_error(self, peer):
        await self.pool.on_peer_error(peer)

    async def getrawtransaction(self, txid: str, verbose=False):
        if txid=='4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b':	
             return {'error code':-5,
                 'error message': 'The genesis block coinbase is not considered an ordinary transaction and cannot be retrieved'}
        a=await self.pool.call('blockchain.transaction.get', txid)
        return a


    async def listunspents_by_address(self, address: str):
        return await self.pool.call('blockchain.address.listunspent', address)

    async def listunspents_by_scripthash(self, scripthash: str, get_peer=False, fail_silent=False):
        return await self.pool.call(
            'blockchain.scripthash.listunspent', scripthash, get_peer=get_peer, fail_silent=fail_silent
        )

    async def getaddresshistory(self, scripthash: str):
        return await self.pool.call('blockchain.address.get_history', scripthash)

    async def get_chunk(self, chunks_index: int, get_peer=False):
        return await self.pool.call('blockchain.block.get_chunk', chunks_index, get_peer=get_peer)

    async def get_merkleproof(self, txid: str, block_height: int):
        return await self.pool.call('blockchain.transaction.get_merkle', txid, block_height)

    async def get_headers_in_range_from_chunks(self, starts_from: int, ends_to: int, get_peer=False):
        futures = []
        for chunk_index in range(starts_from, ends_to):
            futures.append(self.get_headers_from_chunk(chunk_index, get_peer=get_peer))
        headers = []
        if not get_peer:
            for _headers in await asyncio.gather(*futures):
                _headers and headers.extend(_headers)
            return headers
        else:
            peer = None
            for response in await asyncio.gather(*futures):
                response and headers.extend(response[1])
                peer = response[0]
            return peer, headers

    async def get_headers_in_range(self, starts_from: int, ends_to: int):
        chunks_range = [x for x in range(starts_from, ends_to)]
        futures = []
        for i in chunks_range:
            futures.append(self.get_header(i))
        return await asyncio.gather(*futures)

    async def estimatefee(self, blocks: int):
        return await self.pool.call('blockchain.estimatefee', blocks)

    async def get_headers_from_chunk(self, chunk_index: int, get_peer=True):
        peer = None
        if get_peer:
            peer, chunk = await self.get_chunk(chunk_index, get_peer=get_peer)
        else:
            chunk = await self.get_chunk(chunk_index, get_peer=get_peer)
        if not chunk:
            return
        hex_headers = [chunk[i:i + 160] for i in range(0, len(chunk), 160)]
        headers = []
        for i, header_hex in enumerate(hex_headers):
            header = deserialize_header(header_hex)
            header['block_height'] = int(chunk_index * 2016 + i)
            header['header_bytes'] = binascii.unhexlify(header_hex)
            header['block_hash'] = header.pop('hash')
            if header['block_height'] in self._checkpoints:
                if self._checkpoints[header['block_height']] != header['block_hash']:
                    await peer.disconnect()
                    raise exceptions.NetworkHeadersInconsistencyException(
                        'Checkpoint failure. Expected: %s, Failure: %s',
                        self._checkpoints[header['block_height']], header_hex
                    )
            headers.append(header)
        return get_peer and (peer, headers) or headers

    async def start(self):
        self.loop.create_task(self.pool.connect())

    async def disconnect_from_peer(self, peer: ElectrodConnection):
        self.loop.create_task(peer.disconnect())
