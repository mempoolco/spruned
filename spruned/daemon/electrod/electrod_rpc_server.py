from typing import Tuple, Dict
import aiomas
import binascii
from spruned.application.tools import deserialize_header


class ElectrodRPCServer:
    router = aiomas.rpc.Service()

    def __init__(self, endpoint: (str, Tuple), repository):
        self.endpoint = endpoint
        self.interface = None
        self.repo = repository
        self._server_instance = None

    def _serialize_header_as_bitcoind_would_do(self, header):
        _best_header = self.repo.get_best_header()
        _deserialized_header = deserialize_header(header['data'])
        return {
              "hash": _deserialized_header['hash'],
              "confirmations": _best_header['block_height'] - header['block_height'] + 1,
              "height": header['block_height'],
              "version": _deserialized_header['version'],
              "versionHex": "Not Implemented Yet",
              "merkleroot": _deserialized_header['merkle_root'],
              "time": _deserialized_header['timestamp'],
              "mediantime": _deserialized_header['timestamp'],
              "nonce": _deserialized_header['nonce'],
              "bits": _deserialized_header['bits'],
              "difficulty": "Not Implemented Yet",
              "chainwork": "Not Implemented Yet",
              "previousblockhash": _deserialized_header['prev_block_hash'],
              "nextblockhash": header.get('next_block_hash')
            }

    def _serialize_header(self, header: Dict, verbose_mode) -> Dict:
        header['data'] = binascii.hexlify(header['data']).decode()
        if not verbose_mode:
            return {'response': header['data']}
        return self._serialize_header_as_bitcoind_would_do(header)

    def set_interface(self, interface):
        assert not self.interface, "RPC Server already initialized"
        self.interface = interface

    def enable_blocks_api(self):
        pass

    def disable_blocks_api(self):
        pass

    async def start(self):
        server = await aiomas.rpc.start_server(self.endpoint, self)
        self._server_instance = server

    @router.expose
    async def getrawtransaction(self, payload: Dict):
        assert "txid" in payload
        return await self.interface.getrawtransaction(payload["txid"])

    @router.expose
    async def getblockheader(self, payload: Dict):
        assert "block_hash" in payload
        verbose_mode = payload.get('verbose', True)
        header = self.repo.get_block_header(payload["block_hash"])
        return self._serialize_header(header, verbose_mode)

    @router.expose
    async def getblockhash(self, payload: Dict):
        return self.repo.get_block_hash(payload["block_height"])

    @router.expose
    async def sendrawtransaction(self, rawtransaction: str):
        return await self.interface.sendrawtransaction(rawtransaction)

    @router.expose
    async def estimatefee(self, blocks: int):
        return await self.interface.estimatefee(blocks)

    @router.expose
    async def getmempoolinfo(self):
        return await self.interface.getmempoolinfo()

    @router.expose
    async def getbestblockhash(self):
        return self.repo.get_best_header().get('block_hash')

    @router.expose
    async def getblockcount(self):
        return self.repo.get_best_header().get('block_height')
