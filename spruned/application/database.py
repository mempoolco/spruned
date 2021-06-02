import plyvel
from spruned import settings

BRAND_NEW_DB_PLACEHOLDER = b'brand_new_db'


def init_ldb_storage():
    if not settings.TESTING:
        leveldb_settings = dict(
            compression=None,
            block_size=128 * 1024 * 1024
        )
        try:
            _storage_ldb = plyvel.DB(
                settings.LEVELDB_PATH,
                **leveldb_settings
            )
            _storage_ldb.get(BRAND_NEW_DB_PLACEHOLDER)
        except:
            _storage_ldb = plyvel.DB(
                settings.LEVELDB_PATH,
                create_if_missing=True,
                **leveldb_settings
            )
            _storage_ldb.put(BRAND_NEW_DB_PLACEHOLDER, BRAND_NEW_DB_PLACEHOLDER)

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
