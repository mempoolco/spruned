# The MIT License (MIT)
#
# Copyright (c) 2021 - spruned contributors - https://github.com/mempoolco/spruned
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import logging
import time
import typing
from enum import Enum

import lmdb

from spruned.application.tools import dblsha256

DOUBLE_SPEND_ERROR = 990
KILL_PILL_RECEIVED = 991
PARALLEL_SPEND_ERROR = 992
ALONE_WITH_PENDING_UTXO = 993
INVALID_UTXO = 994

EXCEPTION = 999


class ExitException(Exception):
    pass


class DBPrefix(Enum):
    UTXO = 3


class BlockProcessor:
    """
    A multiprocessing-powered blocks processor for UTXO validation and sharding.
    Implementation of the UTXOXO sharding protocol.
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
        shards: int,
        db: lmdb.Environment,
        prev_rounds_processed: typing.List[typing.Dict]
    ):
        self.logger = logging.getLogger('utxo')
        self.block: typing.Dict = block
        self.kill_pill = kill_pill
        self.processing_blocks = processing_blocks
        self.requested_utxo = requested_utxo
        self.published_utxo = published_utxo
        self.done_blocks = done_blocks
        self.total_blocks = total_blocks
        self.shards = shards
        self.prev_rounds_processed = prev_rounds_processed
        self.db = db
        self._missing_txs = []
        self._consumed_utxo = dict()
        self._new_utxo = dict()
        self._new_utxo_k = set()
        self._error = None
        self._exit_code = 0
        self.height_in_bytes = block['height'].to_bytes(4, 'little')

    def _check_kill_pill(self):
        if self.kill_pill:
            return True

    @staticmethod
    def _get_db_key(prefix: DBPrefix, name: bytes = b''):
        assert isinstance(name, bytes)
        return b'%s%s' % (int.to_bytes(prefix.value, 2, "big"), name)

    def _validate_utxo(self, vin: typing.Dict, utxo: bytes):
        """
        Full UTXO validation, scripts % signatures.
        """
        # todo full validation, raise INVALID_UTXO exit code if validation fails.
        pass

    def _get_data_from_prev_chunks(self, outpoint: bytes) -> typing.Optional[typing.List[bytes]]:
        """
        Look for the outpoints produced from the previous chunks of the current round.
        :param outpoint:
        :return:
        """
        for res in self.prev_rounds_processed:
            resp = res['new_utxo'].get(outpoint)
            if resp:
                return resp

    def _process_vin(self, vin, local_utxo: typing.Dict, check_in_db: bool) -> bool:
        """
        Consumes UTXO. In the first round (check_in_db) try to obtain UTXO from the
        DB. Otherwise append its need into the requests storage, so as the other blocks
        can fulfill the requests.
        """
        outpoint = vin['hash'] + vin['index']
        with self.db.begin() as r:
            utxo = r.get(self._get_db_key(DBPrefix.UTXO, outpoint)) if check_in_db else None
        from_db = False
        from_current_round = False
        if utxo:
            from_db = True
            # We have found the UTXO from the DB and we must calculate the shard by ourselves.
            shard = (int.from_bytes(dblsha256(utxo[13:]), 'little') % self.shards).to_bytes(4, 'little')
        if not utxo and check_in_db:
            if utxo in self.requested_utxo:
                self.kill_pill.append(1)
                self._exit_code = PARALLEL_SPEND_ERROR
                self._error = outpoint
                return True
            self.logger.debug('block %s is requesting utxo %s' % (self.block['height'], outpoint))
            self.requested_utxo.append(outpoint)
            return False
        if not utxo:
            # If the utxo comes from another worker, the shard it's already calculated.
            data = self.published_utxo.pop(outpoint, None)
            from_current_round = bool(data)
            data = data or self._get_data_from_prev_chunks(outpoint)
            if not data:
                return False
            utxo, shard = data
        self._validate_utxo(vin, utxo)
        if utxo and (from_db or not from_current_round):
            # Enqueue the UTXO as NEW only if it comes from the database,
            # otherwise it's as we have just never seen it.
            local_utxo[outpoint] = [utxo, shard]
        return True

    def _process_vout(self, tx: typing.Dict, i: int, vout: typing.Dict, is_coinbase: bool):
        """
        Process a transaction output, add UTXO.
        """
        outpoint = tx['hash'] + i.to_bytes(4, 'little')
        if outpoint in self._new_utxo_k:
            self.kill_pill.append(1)
            self._error = outpoint
            self._exit_code = DOUBLE_SPEND_ERROR
        self.logger.debug('block %s adding utxo %s' % (self.block['height'], outpoint))
        shard = (int.from_bytes(dblsha256(vout['script']), 'little') % self.shards).to_bytes(2, 'little')
        db_serialized_vout = vout['amount'] + is_coinbase.to_bytes(1, 'little') + self.height_in_bytes + vout['script']
        self._new_utxo[outpoint] = [db_serialized_vout, shard]
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
            'height': self.block['height'],
            'missing_txs': self._missing_txs,
            'consumed_utxo': self._consumed_utxo,
            'new_utxo': self._new_utxo,
            'error': self._error,
            'exit_code': self._exit_code
        }

    @classmethod
    def process(
            cls,
            block: typing.Dict,
            kill_pill: typing.List,
            processing_blocks: typing.List,
            done_blocks: typing.List,
            requested_utxo: typing.List,
            published_utxo: typing.Dict,
            total_blocks: int,
            shards: int,
            path: str,
            prev_rounds_processed: typing.List[typing.Dict]
    ) -> typing.Dict:
        """
        Processor Entry Point, must be used into Repository.process_blocks
        """
        with lmdb.open(path, readonly=True) as db:
            return cls._process(
                block, kill_pill, processing_blocks, done_blocks, requested_utxo,
                published_utxo, total_blocks, shards, db, prev_rounds_processed
            )

    @classmethod
    def _process(
        cls,
        block: typing.Dict,
        kill_pill: typing.List,
        processing_blocks: typing.List,
        done_blocks: typing.List,
        requested_utxo: typing.List,
        published_utxo: typing.Dict,
        total_blocks: int,
        shards: int,
        db: lmdb.Environment,
        prev_rounds_processed: typing.List[typing.Dict]
    ):
        processing_blocks.append(block['height'])
        self = cls(
            block, kill_pill, processing_blocks,
            done_blocks, requested_utxo, published_utxo,
            total_blocks, shards, db,
            prev_rounds_processed
        )
        try:
            for tx in self.block['txs']:  # first round, process block txs
                try:
                    self._process_tx(tx)
                    self._evade_requested_utxo()  # publish data requested by other workers.
                except ExitException:
                    break
            self._process_missing_txs()  # request data from other workers, as it's not available on the UTXO DB.
            self._check_requested_unspents()  # once missing_txs are processed, publish data for other workers.
        except Exception as e:
            self.logger.exception('Error in main loop')
            self.kill_pill.append(1)  # tell other workers to quit.
            self._exit_code = EXCEPTION  # gracefully exit.
            self._error = str(e)  # take not of the error
        self.logger.debug('block %s exiting' % self.serialize())
        return self.serialize()  # whatever happens, return a serializable output.

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
            self._process_vout(tx, i, vout, bool(tx['gen']))
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
                self.logger.debug('marking block as done, bad, %s' % self.block['height'])
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
                    if next_is_failure < 50:
                        next_is_failure += 1
                    else:
                        self._exit_code = ALONE_WITH_PENDING_UTXO
                        self.kill_pill.append(1)
                        break
                continue
            self.logger.debug('marking block as done, good, %s' % self.block['height'])
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
            time.sleep(0.001)
