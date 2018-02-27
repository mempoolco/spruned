from spruned.abstracts import HeadersRepository
from spruned.daemon import database


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

    def save_header(self, blockhash: str, blockheight: int, headerbytes: bytes, prev_block_hash: str):
        # FIXME - Saving is a bit intensive. Find transactional points.
        session = self.session()

        def _save():
            try:
                model = database.Header(blockhash=blockhash, blockheight=blockheight, data=headerbytes)
                session.add(model)
                session.flush()
                session.commit()
            finally:
                session.close()

        existing = session.query(database.Header).filter_by(blockheight=blockheight).one_or_none()
        if existing:
            assert existing.blockhash == blockhash
            return
        if blockheight == 0:
            _save()
        else:
            prev_block = session.query(database.Header).filter_by(blockheight=blockheight-1).one()
            assert prev_block.blockhash == prev_block_hash
            _save()
