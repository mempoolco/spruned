from spruned import settings
from spruned.application.database import init_ldb_storage
from spruned.repositories.blocks_diskdb import BlocksDiskDB
from spruned.repositories.utxo_diskdb import UTXODiskDB

blockchain_level_db = init_ldb_storage(settings.LEVELDB_INDEX_PATH)
blockchain_disk_db = BlocksDiskDB(settings.BLOCKS_PATH)

utxo_level_db = init_ldb_storage(settings.UTXO_INDEX_PATH)
utxo_disk_db = UTXODiskDB(settings.UTXO_REV_STATE_PATH)
