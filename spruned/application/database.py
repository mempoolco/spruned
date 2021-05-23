import plyvel
from spruned import settings


def init_ldb_storage():
    if not settings.TESTING:
        _storage_ldb = plyvel.DB(
            settings.LEVELDB_PATH,
            create_if_missing=True
        )
    else:
        from unittest.mock import Mock
        _storage_ldb = Mock()
    return _storage_ldb


level_db = init_ldb_storage()


def erase_ldb_storage():
    path = settings.LEVELDB_PATH
    import os
    if os.environ.get('TESTING'):
        raise ValueError('cannot delete a db in a test env')
    for f in os.listdir(path):
        os.remove(path + '/' + f)
    os.rmdir(path)
