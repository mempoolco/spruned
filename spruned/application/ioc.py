from spruned import settings
from spruned.application.database import init_ldb_storage


blockchain_level_db = init_ldb_storage(settings.LEVELDB_INDEX_PATH)