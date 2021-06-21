import logging
import time
import typing

import rocksdb

DOUBLE_SPEND_ERROR = 990
KILL_PILL_RECEIVED = 991
PARALLEL_SPEND_ERROR = 992
ALONE_WITH_PENDING_UTXO = 993
INVALID_UTXO = 994

EXCEPTION = 999


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
        done_blocks: typing.List,
        requested_utxo: typing.List,
        published_utxo: typing.Dict,
        total_blocks: int,
        db_path='/tmp/prova/provaz',
    ):
        self.block: typing.Dict = block
        self.kill_pill = kill_pill
        self.processing_blocks = processing_blocks
        self.requested_utxo = requested_utxo
        self.published_utxo = published_utxo
        self.done_blocks = done_blocks
        self.total_blocks = total_blocks

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

    def _validate_utxo(self, vin: typing.Dict, utxo: bytes):
        """
        Full UTXO validation, scripts % signatures.
        """
        # todo full validation, raise INVALID_UTXO exit code if validation fails.
        pass

    def _process_vin(self, vin, local_utxo: typing.Dict, check_in_db) -> bool:
        """
        Consumes UTXO. In the first round (check_in_db) try to obtain UTXO from the
        DB. Otherwise append into the requests storage,
        so as the other blocks can fulfill the requests.
        """
        outpoint = vin['hash'] + vin['index']
        utxo = check_in_db and self.db.get(outpoint)
        if not utxo and check_in_db:
            if utxo in self.requested_utxo:
                self.kill_pill.append(1)
                self._exit_code = PARALLEL_SPEND_ERROR
                self._error = outpoint
                return True
            self.logger.debug('block %s is requesting utxo %s' % (self.block['height'], outpoint))
            self.requested_utxo.append(outpoint)
            return False

        utxo = utxo or self.published_utxo.pop(outpoint, None)
        if not utxo:
            return False
        self._validate_utxo(vin, utxo)
        local_utxo[outpoint] = utxo
        return True

    def _process_vout(self, tx: typing.Dict, i: int, vout: typing.Dict):
        """
        Process a transaction output, add UTXO.
        """
        outpoint = tx['hash'] + i.to_bytes(4, 'little')
        if outpoint in self._new_utxo_k:
            self.kill_pill.append(1)
            self._error = outpoint
            self._exit_code = DOUBLE_SPEND_ERROR
        self.logger.debug('block %s adding utxo %s' % (self.block['height'], outpoint))
        self._new_utxo[outpoint] = vout['script'] + vout['amount']
        self._new_utxo_k.add(outpoint)

    def _evade_requested_utxo(self):
        """
        Used into multiple methods, check if other workers are requesting
        an UTXO produced by the local block.
        At the same time that the UTXO is passed into the shared memory, is removed from the
        outcome (the new utxo that are going to be saved into the DB).
        """
        if not self.requested_utxo:
            return
        self.logger.debug('found requested utxo: %s' % self.requested_utxo)
        requested_utxo = set(self.requested_utxo) & set(self._new_utxo_k)
        for r in requested_utxo:
            self.logger.debug('block %s is providing utxo %s' % (self.block['height'], r))
            self.requested_utxo.remove(r)
            assert not self.published_utxo.get(r)
            self.published_utxo[r] = self._new_utxo.pop(r)
            self._new_utxo_k.remove(r)

    def serialize(self) -> typing.Dict:
        return {
            'block_height': self.block['height'],
            'missing_txs': self._missing_txs,
            'consumed_utxo': self._consumed_utxo,
            'new_utxo': self._new_utxo,
            'error': self._error,
            'exit_code': self._exit_code
        }

    @classmethod
    def process(
            cls, block, kill_pill, processing_blocks,
            done_blocks, requested_utxo, published_utxo, total_blocks, path
    ) -> typing.Dict:
        """
        Processor Entry Point, must be used into Repository.process_blocks
        """
        processing_blocks.append(block['height'])
        self = cls(
            block, kill_pill, processing_blocks,
            done_blocks, requested_utxo, published_utxo, total_blocks, path
        )
        try:
            for tx in self.block['txs']:
                try:
                    self._process_tx(tx)
                    self._evade_requested_utxo()
                except ExitException:
                    break
            self._process_missing_txs()
            self._check_requested_unspents()
        except Exception as e:
            self.logger.exception('Error in main loop')
            self.kill_pill.append(1)
            self._exit_code = EXCEPTION
            self._error = str(e)
        return self.serialize()

    def _process_tx(self, tx, check_in_db=True):
        """
        Process a transaction for UTXO validation.
        Used both in the first round (blocks transactions)
        and in the second (reprocess missing txs).
        """
        if self._exit_code:
            raise ExitException
        if self.kill_pill:
            self._exit_code = KILL_PILL_RECEIVED
            raise ExitException
        local_utxo = dict()
        if not tx['gen']:
            for vin in tx['ins']:
                if self._exit_code:
                    raise ExitException
                this_round = self._process_vin(vin, local_utxo, check_in_db)
                if not this_round:
                    check_in_db and tx not in \
                        self._missing_txs and self._missing_txs.append(tx)
                    return
        self._consumed_utxo.update(local_utxo)
        for i, vout in enumerate(tx['outs']):
            self._process_vout(tx, i, vout)
        return True

    def _process_missing_txs(self):
        """
        Process missing txs, expecting other workers
        to provide the UTXO not available from the database.
        """
        next_is_failure = 0
        while 1:
            self._evade_requested_utxo()
            if self._exit_code:
                self.done_blocks.append(self.block['height'])
                break
            ok = []
            for tx in self._missing_txs:
                if not self._process_tx(tx, check_in_db=False):
                    break
                ok.append(tx)
            self._missing_txs = [x for x in self._missing_txs if x not in ok]
            if self._missing_txs:
                if len(self.done_blocks) == self.total_blocks - 1:
                    if next_is_failure < 100:
                        next_is_failure += 1
                    else:
                        self._exit_code = ALONE_WITH_PENDING_UTXO
                        self.kill_pill.append(1)
                        break
                continue
            self.done_blocks.append(self.block['height'])
            break

    def _check_requested_unspents(self):
        """
        Check if other workers are requesting an UTXO processed by the current block.
        If the missing UTXO is found in the local round, pushes it into the shared memory.
        """
        while 1:
            self.logger.debug('block %s is polling needs: %s/%s' % (
                self.block['height'], self.done_blocks, self.total_blocks
            ))
            if self.kill_pill:
                self._exit_code = KILL_PILL_RECEIVED
                break
            if len(self.done_blocks) == self.total_blocks:
                break
            self._evade_requested_utxo()
            time.sleep(0.01)
