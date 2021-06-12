from spruned import settings
from spruned.application.database import init_ldb_storage, init_disk_db


level_db = init_ldb_storage(settings.LEVELDB_INDEX_PATH)
disk_db = init_disk_db(settings.BLOCKS_PATH)
