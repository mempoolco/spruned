from typing import List, Dict

import binascii

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from spruned.application.abstracts import HeadersRepository
from spruned.application.logging_factory import Logger
from spruned.application.tools import verify_pow
from spruned.daemon import exceptions
from spruned.application import database


class HeadersSQLiteRepository(HeadersRepository):
    def __init__(self, session):
        self.session = session
        self._cache = None

    def set_cache(self, cache):
        self._cache = cache

    @staticmethod
    def _header_model_to_dict(header: database.Header, nextblockhash: (None, str), prevblockhash: (None, str)) -> Dict:
        res = {
            'block_height': header.blockheight,
            'block_hash': binascii.hexlify(header.blockhash).decode(),
            'header_bytes': header.data,
            'next_block_hash': nextblockhash and binascii.hexlify(nextblockhash).decode(),
            'prev_block_hash': prevblockhash and binascii.hexlify(prevblockhash).decode()
        }
        if not res['prev_block_hash']:
            res.pop('prev_block_hash')
        if not res['next_block_hash']:
            res.pop('next_block_hash')
        return res

    def get_best_blockhash(self) -> str:
        session = self.session()
        _id = session.query(func.max(database.Header.id)).one_or_none()
        best_header = _id and session.query(database.Header).filter_by(id=_id[0]).one_or_none()
        best_blockhash = best_header and best_header.blockhash
        return best_blockhash and binascii.hexlify(best_blockhash).decode()

    def get_best_header(self):
        best_blockhash = self.get_best_blockhash()
        return best_blockhash and self.get_block_header(best_blockhash)

    def get_header_at_height(self, height: int):
        blockhash = self.get_block_hash(height)
        return self.get_block_header(blockhash)

    def get_headers_since_height(self, height: int, limit=None):
        session = self.session()
        query = session.query(database.Header).filter(database.Header.blockheight >= height)\
            .order_by(database.Header.blockheight.asc())
        if limit is not None:
            query = query.limit(limit)
        headers = query.all()
        res = []
        howmany = len(headers)
        for i, h in enumerate(headers):
            if not i:
                prevblockhash = h.blockheight != 0 and self.get_block_hash(h.blockheight-1, decode=False)
            else:
                prevblockhash = headers[i-1].blockhash
            nextblockhash = i + 1 < howmany and headers[i + 1].blockhash or self.get_block_hash(
                h.blockheight + 1, decode=False
            )
            res.append(
                self._header_model_to_dict(
                    h,
                    nextblockhash=nextblockhash,
                    prevblockhash=prevblockhash
                )
            )
        return res

    @database.atomic
    def save_header(self, blockhash: str, blockheight: int, headerbytes: bytes, prev_block_hash: str):
        session = self.session()

        def _save():
            model = database.Header(
                blockhash=binascii.unhexlify(blockhash),
                blockheight=blockheight,
                data=headerbytes
            )
            session.add(model)
            try:
                session.flush()
            except IntegrityError:
                raise exceptions.HeadersInconsistencyException
            return model

        if blockheight == 0:
            model = _save()
            prev_block = None
        else:
            prev_block = session.query(database.Header).filter_by(blockheight=blockheight - 1).one()
            if not prev_block or prev_block.blockhash != binascii.unhexlify(prev_block_hash):
                raise exceptions.HeadersInconsistencyException

            model = _save()
        return model and self._header_model_to_dict(
            model, prevblockhash=prev_block and prev_block.blockhash, nextblockhash=None
        )

    @database.atomic
    def save_headers(self, headers: List[Dict]):
        session = self.session()
        for i, header in enumerate(headers):
            verify_pow(header['header_bytes'], binascii.unhexlify(header['block_hash']))
            if i == 0 and header['block_height'] != 0:
                prev_block = session.query(database.Header).filter_by(blockheight=header['block_height'] - 1).one()
                if prev_block.blockhash != binascii.unhexlify(header['prev_block_hash']):
                    Logger.repository.exception('Integrity Error on check prev block hash')
                    raise exceptions.HeadersInconsistencyException
            model = database.Header(
                blockhash=binascii.unhexlify(header['block_hash']),
                blockheight=header['block_height'],
                data=header['header_bytes']
            )
            session.add(model)
        try:
            session.flush()
        except (IntegrityError, AssertionError) as e:
            Logger.repository.exception('Integrity Error on save_headers')
            raise exceptions.HeadersInconsistencyException
        return headers

    @database.atomic
    def remove_headers_after_height(self, blockheight: int):
        session = self.session()
        headers = session.query(database.Header).filter(database.Header.blockheight >= blockheight).all()
        for header in headers:
            session.delete(header)
        session.flush()

    @database.atomic
    def remove_header_at_height(self, blockheight: int) -> Dict:
        session = self.session()
        header = session.query(database.Header).filter(database.Header.blockheight == blockheight).one()
        removing_dict = self._header_model_to_dict(header, "", "")
        session.delete(header)
        session.flush()
        return removing_dict

    def get_block_hash(self, blockheight: int, decode=True):
        session = self.session()
        header = session.query(database.Header).filter_by(blockheight=blockheight).one_or_none()
        if not header:
            return
        if decode:
            return binascii.hexlify(header.blockhash).decode()
        return header.blockhash

    def get_block_height(self, blockhash: str):
        session = self.session()
        header = session.query(database.Header).filter_by(blockhash=binascii.unhexlify(blockhash)).one_or_none()
        return header and header.blockheight

    def get_block_header(self, blockhash: str):
        session = self.session()
        header = session.query(database.Header).filter_by(blockhash=binascii.unhexlify(blockhash)).one_or_none()
        if not header:
            return
        prev_next = session.query(database.Header).filter(database.Header.id.in_((header.id-1, header.id+1))).all()
        prevblockhash = nextblockhash = None
        for h in prev_next:
            if h.id == header.id - 1:
                prevblockhash = h.blockhash
            elif h.id == header.id + 1:
                nextblockhash = h.blockhash
        return self._header_model_to_dict(header, nextblockhash, prevblockhash)
