from typing import List, Dict
from sqlalchemy.exc import IntegrityError
from spruned.abstracts import HeadersRepository
from spruned.daemon import database, exceptions


class HeadersSQLiteRepository(HeadersRepository):
    def __init__(self, session):
        self.session = session

    @staticmethod
    def _header_model_to_dict(header: database.Header) -> Dict:
        return {
            'block_height': header.blockheight,
            'block_hash': header.blockhash,
            'data': header.data
        }

    def get_best_header(self):
        session = self.session()
        res = session.query(database.Header).order_by(database.Header.blockheight.desc()).limit(1).one_or_none()
        res = res and self._header_model_to_dict(res)
        print('Best header requested, res: %s' % res)
        return res

    def get_header_at_height(self, height: int):
        blockhash = self.get_block_hash(height)
        return self.get_block_header(blockhash)

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

    @database.atomic
    def save_headers(self, headers: List[Dict]):
        session = self.session()
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
            print('Inconsistency error: %s' % e)
            raise exceptions.HeadersInconsistencyException

    @database.atomic
    def remove_headers_since_height(self, blockheight: int):
        session = self.session()
        headers = session.query(database.Header).filter(database.Header.blockheight >= blockheight).all()
        for header in headers:
            session.delete(header)
        session.flush()

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
        return header and self._header_model_to_dict(header)
