import asyncio
import binascii
from typing import Dict
from spruned.application.context import ctx
from spruned.application.exceptions import InvalidPOWException, InvalidHeaderException
from spruned.application.logging_factory import Logger
from spruned.services import exceptions
from spruned.application.tools import blockheader_to_blockhash, deserialize_header, serialize_header
from spruned.application.consensus import verify_pow
from spruned.services.electrum.electrum_connection import ElectrumConnectionPool, ElectrumConnection
from spruned.services.electrum.electrum_fee_estimation import EstimateFeeConsensusProjector, \
    EstimateFeeConsensusCollector


class ElectrumInterface:
    def __init__(
            self,
            connection_pool: ElectrumConnectionPool,
            loop=asyncio.get_event_loop(),
            fees_projector: EstimateFeeConsensusProjector = None,
            fees_collector: EstimateFeeConsensusCollector = None
    ):
        self._network = ctx.get_network()
        self.pool = connection_pool
        self._checkpoints = self._network['checkpoints']
        self.loop = loop
        self._fees_projector = fees_projector
        self._fees_collector = fees_collector
        self._collector_bootstrap = False

    async def bootstrap_collector(self):
        if not self._collector_bootstrap:
            self._collector_bootstrap = True

            async def bootstrap(this):
                rates = [2, 6, 36, 4, 100]
                collectors = []
                for rate in rates:
                    if not self._fees_collector.get_rates(rate):
                        collectors.append(this._fees_collector.collect(rate))
                if collectors:
                    await asyncio.gather(*collectors)
                await asyncio.sleep(60)
                self.loop.create_task(bootstrap(this))

            self.loop.create_task(bootstrap(self))

    @property
    def is_pool_online(self):  # pragma: no cover
        return self.pool.is_online()

    def _parse_header(self, electrum_header: Dict):
        if electrum_header.get('hex'):
            header_hex = electrum_header['hex']
            # protocol 1.4
        else:
            header_hex = serialize_header(electrum_header)
            electrum_header['height'] = electrum_header['block_height']
            # some servers with protocol 1.4 that answers with 1.2 expected answer :-(
        blockhash_from_header = blockheader_to_blockhash(header_hex)
        if electrum_header['height'] in self._checkpoints:
            if self._checkpoints[electrum_header['height']] != blockhash_from_header:
                raise exceptions.NetworkHeadersInconsistencyException

        header_data = deserialize_header(header_hex)
        header_bytes = binascii.unhexlify(header_hex)
        verify_pow(header_bytes, binascii.unhexlify(header_data['hash']))
        return {
            'block_hash': blockhash_from_header,
            'block_height': electrum_header['height'],
            'header_bytes': header_bytes,
            'prev_block_hash': header_data['prev_block_hash'],
            'timestamp': header_data['timestamp']
        }

    def add_header_subscribe_callback(self, callback: callable):
        async def parse_and_go(peer, res):
            try:
                header = self._parse_header(res)
                return await callback(peer, header)
            except InvalidPOWException:
                Logger.electrum.error('Wrong POW for header %s from peer %s. Banning', res, peer)
                self.loop.create_task(peer.disconnect())
        self.pool.add_header_observer(parse_and_go)

    def add_on_connected_callback(self, callback: callable):
        self.pool.add_on_connected_observer(callback)

    async def get_header(self, height: int, fail_silent_out_of_range=False, get_peer=False):
        try:
            response = await self.pool.call(
                'blockchain.block.get_header', height, get_peer=True
            )
            peer, header = response
            if header and header.get('code') == 1:
                raise exceptions.ElectrumMissingResponseException
        except exceptions.ElectrumMissingResponseException:
            if fail_silent_out_of_range:
                return
            raise
        try:
            parsed_header = self._parse_header(header)
        except KeyError:
            Logger.p2p.error('Error with header: %s', header, exc_info=True)
            return
        except (exceptions.NetworkHeadersInconsistencyException, InvalidPOWException, InvalidHeaderException):
            Logger.electrum.error('Wrong POW for header %s from peer %s. Banning', header, peer)
            self.loop.create_task(peer.disconnect())
            return

        if not get_peer:
            return parsed_header
        return peer, parsed_header

    async def handle_peer_error(self, peer: ElectrumConnection):
        await self.pool.on_peer_error(peer)

    async def getrawtransaction(self, txid: str, verbose: bool = False):
        if txid == self._network['tx0']:
            raise exceptions.GenesisTransactionRequestedException
        response = await self.pool.call('blockchain.transaction.get', txid, int(verbose))
        if isinstance(response, dict) and (response.get('code') == 2 or 'error' in response.get('message', '')):
            Logger.electrum.warning('getrawtransaction error response: %s' % response)
            return
        return response

    async def listunspents_by_address(self, address: str):
        return await self.pool.call('blockchain.address.listunspent', address)

    async def listunspents_by_scripthash(self, scripthash: str, get_peer=False, fail_silent=False):
        return await self.pool.call(
            'blockchain.scripthash.listunspent', scripthash, get_peer=get_peer, fail_silent=fail_silent
        )

    async def getaddresshistory(self, scripthash: str):
        return await self.pool.call('blockchain.address.get_history', scripthash)

    async def get_headers(self, height: int, count=2016, get_peer=False):
        return await self.pool.call('blockchain.block.headers', height, count, get_peer=get_peer)

    async def get_merkleproof(self, txid: str, block_height: int):
        return await self.pool.call('blockchain.transaction.get_merkle', txid, block_height)

    async def get_headers_in_range_from_chunks(self, starts_from: int, ends_to: int, get_peer: bool = False):
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
        return [h for h in await asyncio.gather(*futures) if h]

    async def estimatefee(self, blocks: int):
        try:
            if not self._fees_collector.get_rates(blocks):
                await self._fees_collector.collect(rate=blocks)
            rates = self._fees_collector.get_rates(blocks)
            if not rates:
                raise exceptions.NoQuorumOnResponsesException
            projection = self._fees_projector.project(rates)
            for d in projection["disagree"]:
                self.pool.get_peer_for_hostname(d).disconnect()
            if projection["agree"]:
                return projection
        except:
            Logger.electrum.exception('Fee estimation error')
            raise exceptions.MissingResponseException

    async def get_headers_from_chunk(self, chunk_index: int, get_peer: bool = True):
        chunk = peer = None
        if get_peer:
            res = await self.get_headers(chunk_index * 2016, get_peer=get_peer)
            if res:
                peer, chunk = res
        else:
            chunk = await self.get_headers(chunk_index * 2016, get_peer=get_peer)

        if not chunk or 'hex' not in chunk:
            return

        chunk = chunk['hex']

        try:
            hex_headers = [chunk[i:i + 160] for i in range(0, len(chunk), 160)]
        except TypeError as e:
            raise exceptions.BrokenDataException from e
        headers = []
        for i, header_hex in enumerate(hex_headers):
            header = deserialize_header(header_hex)
            header['block_height'] = int(chunk_index * 2016 + i)
            header['header_bytes'] = binascii.unhexlify(header_hex)
            header['block_hash'] = header.pop('hash')
            if header['block_height'] in self._checkpoints:
                if self._checkpoints[header['block_height']] != header['block_hash']:
                    peer and await peer.disconnect()
                    raise exceptions.NetworkHeadersInconsistencyException(
                        'Checkpoint failure. Expected: %s, Failure: %s',
                        self._checkpoints[header['block_height']], header['block_hash']
                    )
            headers.append(header)
        return get_peer and (peer, headers) or headers

    async def start(self):
        self.loop.create_task(self.pool.connect())

    async def disconnect_from_peer(self, peer: ElectrumConnection):
        self.loop.create_task(peer.disconnect())

    async def sendrawtransaction(self, rawtx: str, allowhighfees: bool = False):
        return await self.pool.call('blockchain.transaction.broadcast', rawtx)

    def get_connections(self):
        return self.pool.established_connections
