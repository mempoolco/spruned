import asyncio
import logging
import time
from concurrent.futures.process import ProcessPoolExecutor
from concurrent.futures.thread import ThreadPoolExecutor
import typing

import rocksdb

loop = asyncio.get_event_loop()
executor = ProcessPoolExecutor(4)
threaded = ThreadPoolExecutor(4)

DOUBLE_SPEND_ERROR = 990
KILL_PILL_RECEIVED = 991
PARALLEL_SPEND_ERROR = 992


class ExitException(Exception):
    pass


class BlockProcessor:
    """
    A multiprocessing-designed blocks processor and UTXO validator.
    """
    def __init__(
        self,
        block: typing.Dict,
        # the following objects must be multiprocessing.Manager proxies.
        kill_pill: typing.List,
        processing_blocks: typing.List,
        requested_utxo: typing.List,
        published_utxo: typing.Dict,
        db_path='/tmp/prova/provaz'
    ):
        self.block: typing.Dict = block
        self.kill_pill = kill_pill
        self.processing_blocks = processing_blocks
        self.requested_utxo = requested_utxo
        self.published_utxo = published_utxo

        self.db = rocksdb.DB(db_path, rocksdb.Options(), read_only=True)
        self._missing_txs = []
        self._consumed_utxo = dict()
        self._new_utxo = dict()
        self._new_utxo_k = set()
        self._error = None
        self._exit_code = 0
        self.logger = logging.getLogger('utxo')

    def _check_kill_pill(self):
        if self.kill_pill:
            return True

    def _process_vin(self, vin, local_utxo: typing.Dict, check_in_db) -> bool:
        outpoint = vin['outpoint']
        utxo = check_in_db and self.db.get(outpoint)
        if not utxo and check_in_db:
            if utxo in self.requested_utxo:
                self.kill_pill.append(1)
                self._exit_code = PARALLEL_SPEND_ERROR
                self._error = outpoint
                return True
            self.requested_utxo.append(outpoint)
            return False
        elif not utxo:
            if outpoint in self.published_utxo:
                utxo = self.published_utxo.pop(outpoint)
        assert utxo
        # todo full validation
        local_utxo[outpoint] = utxo
        return True

    def _process_vout(self, tx: typing.Dict, i: int, vout: typing.Dict):
        outpoint = tx['hash'] + i.to_bytes(4, 'little')
        if outpoint in self._new_utxo_k:
            self.kill_pill.append(1)
            self._error = outpoint
            self._exit_code = DOUBLE_SPEND_ERROR
        self._new_utxo[outpoint] = vout['script'] + vout['amount']
        self._new_utxo_k.add(outpoint)

    def _check_requested_utxo(self):
        requested_utxo = set(self.requested_utxo) & set(self._new_utxo_k)
        for r in requested_utxo:
            self.requested_utxo.remove(r)
            self.published_utxo[r] = self._new_utxo[r]
            self._new_utxo_k.remove(r)
            self._new_utxo.pop(r)

    def serialize(self) -> typing.Dict:
        return {
            'missing_txs': self._missing_txs,
            'consumed_utxo': self._consumed_utxo,
            'new_utxo': self._new_utxo,
            'error': self._error,
            'exit_code': self._exit_code
        }

    @classmethod
    def process(
            cls, block, kill_pill, processing_blocks, requested_utxo, published_utxo, path
    ) -> typing.Dict:
        self = cls(block, kill_pill, processing_blocks, requested_utxo, published_utxo, path)
        try:
            for tx in self.block['txs']:
                try:
                    self._process_tx(tx)
                    self._check_requested_utxo()
                except ExitException:
                    break
        except Exception as e:
            self.logger.exception('Error in main loop')
            self.kill_pill.append(1)
            raise

        self._process_missing_txs()
        self.processing_blocks.pop(self.block['height'])
        return self.serialize()

    def _process_tx(self, tx, check_in_db=True):
        if self._exit_code:
            raise ExitException
        if self.kill_pill:
            self._exit_code = KILL_PILL_RECEIVED
            raise ExitException
        local_utxo = dict()
        for vin in tx['ins']:
            this_round = self._process_vin(vin, local_utxo, check_in_db)
            if not this_round:
                self._missing_txs.append(tx)
                return
        self._consumed_utxo.update(local_utxo)
        for i, vout in enumerate(tx['outs']):
            self._process_vout(tx, i, vout)

    def _process_missing_txs(self):
        if not self._missing_txs:
            return
        while 1:
            if min(self.processing_blocks) < self.block['height']:
                self.kill_pill.append(1)
                break
            for tx in self._missing_txs:
                self._process_tx(tx, check_in_db=False)
            time.sleep(0.01)
