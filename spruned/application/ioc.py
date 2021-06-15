from spruned import settings
from spruned.application.database import init_ldb_storage
from spruned.repositories.blocks_diskdb import BlocksDiskDB

blockchain_level_db = init_ldb_storage(settings.LEVELDB_INDEX_PATH)
blockchain_disk_db = BlocksDiskDB(settings.BLOCKS_PATH)
