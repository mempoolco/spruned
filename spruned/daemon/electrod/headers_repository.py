from typing import List, Dict
from sqlalchemy.exc import IntegrityError
from spruned.application.abstracts import HeadersRepository
from spruned.application.logging_factory import Logger
from spruned.daemon import database, exceptions


class HeadersSQLiteRepository(HeadersRepository):
    def __init__(self, session):
        self.session = session

    @staticmethod
    def _header_model_to_dict(header: database.Header, nextblockhash: str) -> Dict:
        return {
            'block_height': header.blockheight,
            'block_hash': header.blockhash,
            'data': header.data,
            'next_block_hash': nextblockhash
        }

    def get_best_header(self):
        session = self.session()
        res = session.query(database.Header).order_by(database.Header.blockheight.desc()).limit(1).one_or_none()
        res = res and self._header_model_to_dict(res, None)
        return res

    def get_header_at_height(self, height: int):
        blockhash = self.get_block_hash(height)
        return self.get_block_header(blockhash)

    def get_headers_since_height(self, height: int):
        session = self.session()
        headers = session.query(database.Header).filter(database.Header.blockheight >= height)\
            .order_by(database.Header.blockheight.asc()).all()
        return headers and [
            self._header_model_to_dict(h, self.get_block_hash(h.blockheight+1)) for h in headers
        ] or []

    @database.atomic
    def save_header(self, blockhash: str, blockheight: int, headerbytes: bytes, prev_block_hash: str):
        session = self.session()

        def _save():
            model = database.Header(blockhash=blockhash, blockheight=blockheight, data=headerbytes)
            session.add(model)
            try:
                session.flush()
            except IntegrityError:
                raise exceptions.HeadersInconsistencyException

        if blockheight == 0:
            _save()
        else:
            prev_block = session.query(database.Header).filter_by(blockheight=blockheight-1).one()
            assert prev_block.blockhash == prev_block_hash
            _save()
        return {
            'block_hash': blockheight,
            'block_height': blockheight,
            'prev_block_hash': prev_block_hash,
            'header_bytes': headerbytes
        }

    @database.atomic
    def save_headers(self, headers: List[Dict], force=False):
        session = self.session()
        if force:
            starts_from = headers[0]['block_height']
            ends_to = headers[-1]['block_height']
            existings = session.query(database.Header)\
                .filter(database.Header.blockheight >= starts_from).filter(database.Header.blockheight <= ends_to).all()
            _ = [session.delete(existing) for existing in existings]
            Logger.repository.debug(
                'Force mode, deleted headers from %s to %s (included)', starts_from, ends_to
            )
            session.flush()
        for i, header in enumerate(headers):
            if i == 0 and header['block_height'] != 0:
                prev_block = session.query(database.Header).filter_by(blockheight=header['block_height'] - 1).one()
                assert prev_block.blockhash == header['prev_block_hash']
            model = database.Header(
                blockhash=header['block_hash'],
                blockheight=header['block_height'],
                data=header['header_bytes']
            )
            session.add(model)
        try:
            session.flush()
        except IntegrityError as e:
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
        removing_dict = self._header_model_to_dict(header, "")
        session.delete(header)
        session.flush()
        return removing_dict

    def get_block_hash(self, blockheight: int):
        session = self.session()
        header = session.query(database.Header).filter_by(blockheight=blockheight).one_or_none()
        return header and header.blockhash

    def get_block_height(self, blockhash: str):
        session = self.session()
        header = session.query(database.Header).filter_by(blockhash=blockhash).one_or_none()
        return header and header.blockheight

    def get_block_header(self, blockhash: str):
        session = self.session()
        header = session.query(database.Header).filter_by(blockhash=blockhash).one_or_none()
        nextblockhash = self.get_block_hash(header.blockheight + 1)
        return header and self._header_model_to_dict(header, nextblockhash)
