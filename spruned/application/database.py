import plyvel
import rocksdb

from spruned import settings

BRAND_NEW_DB_PLACEHOLDER = b'spruned-ldb'


def init_rocksdb_storage(rocksdb_path: str):
    try:
        db = rocksdb.DB(rocksdb_path, rocksdb.Options())
        assert db.get(BRAND_NEW_DB_PLACEHOLDER)
    except:
        db = rocksdb.DB(rocksdb_path, rocksdb.Options(
            create_if_missing=True,
            compression=rocksdb.CompressionType.no_compression))
        db.put(BRAND_NEW_DB_PLACEHOLDER, BRAND_NEW_DB_PLACEHOLDER)
    return db


def init_ldb_storage(leveldb_path: str):
    leveldb_settings = dict(compression=None)
    try:
        _storage_ldb = plyvel.DB(
            leveldb_path,
            **leveldb_settings
        )
        _storage_ldb.get(BRAND_NEW_DB_PLACEHOLDER)
    except:
        _storage_ldb = plyvel.DB(
            leveldb_path,
            create_if_missing=True,
            **leveldb_settings
        )
        _storage_ldb.put(BRAND_NEW_DB_PLACEHOLDER, BRAND_NEW_DB_PLACEHOLDER)
    return _storage_ldb


def erase_ldb_storage():
    path = settings.LEVELDB_INDEX_PATH
    import os
    if os.environ.get('TESTING'):
        raise ValueError('cannot delete a db in a test env')
    for f in os.listdir(path):
        os.remove(path + '/' + f)
    os.rmdir(path)
