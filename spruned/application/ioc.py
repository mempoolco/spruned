from spruned import settings
from spruned.application.database import init_lmdb
from spruned.application.manager import get_manager
from spruned.repositories.blocks_diskdb import BlocksDiskDB
from spruned.repositories.utxo_diskdb import UTXODiskDB

blockchain_db = init_lmdb(settings.LEVELDB_INDEX_PATH)
blockchain_disk_db = BlocksDiskDB(settings.BLOCKS_PATH)

utxo_db = init_lmdb(settings.UTXO_INDEX_PATH)
utxo_disk_db = UTXODiskDB(settings.UTXO_REV_STATE_PATH)

manager = get_manager()
