import lmdb

BRAND_NEW_DB_PLACEHOLDER = b'spruned-db'


def init_lmdb(lmdb_path: str, readonly=False):
    db = None
    try:
        db = lmdb.open(
            lmdb_path,
            map_size=28991029248,
            readonly=readonly,
            create=False
        )
        assert db.begin().get(BRAND_NEW_DB_PLACEHOLDER)
    except:
        db and db.close()
        db = lmdb.open(
            lmdb_path,
            map_size=28991029248,
            readonly=readonly,
            create=True
        )
        with db.begin(write=True) as tx:
            tx.put(BRAND_NEW_DB_PLACEHOLDER, BRAND_NEW_DB_PLACEHOLDER)
    return db
