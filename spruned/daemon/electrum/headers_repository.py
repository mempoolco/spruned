from typing import List, Dict
from sqlalchemy.exc import IntegrityError
from spruned.abstracts import HeadersRepository
from spruned.daemon import database, exceptions


class HeadersSQLiteRepository(HeadersRepository):
    def __init__(self, session):
        self.session = session

    def get_best_header(self):
        session = self.session()
        res = session.query(database.Header).order_by(database.Header.blockheight.desc()).limit(1).one_or_none()
        res = res and {
            'block_height': res.blockheight,
            'block_hash': res.blockhash,
            'data': res.data
        }
        print('Best header requested, res: %s' % res)
        return res

    def get_header_at_height(self, height: int):
        pass

    def get_header_for_hash(self, blockhash: str):
        pass

    @database.atomic
    def save_header(self, blockhash: str, blockheight: int, headerbytes: bytes, prev_block_hash: str):
        # FIXME - Saving is a bit intensive. Find transactional points.
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
        except IntegrityError:
            raise exceptions.HeadersInconsistencyException





    @database.atomic
    def remove_headers_since_height(self, blockheight: int):
        session = self.session()
        headers = session.query(database.Header).filter(database.Header.blockheight >= blockheight).all()
        _ = (session.delete(header) for header in headers)
        return True
