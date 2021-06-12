import plyvel
from aiodiskdb import AioDiskDB

from spruned import settings

BRAND_NEW_DB_PLACEHOLDER = b'brand_new_db'


def init_ldb_storage(leveldb_path: str):
    leveldb_settings = dict(
        compression=None,
        block_size=16 * 1024 * 1024
    )
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


def init_disk_db(diskdb_path: str):
    return AioDiskDB(
        diskdb_path,
        create_if_not_exists=True
    )


def erase_ldb_storage():
    path = settings.LEVELDB_INDEX_PATH
    import os
    if os.environ.get('TESTING'):
        raise ValueError('cannot delete a db in a test env')
    for f in os.listdir(path):
        os.remove(path + '/' + f)
    os.rmdir(path)
