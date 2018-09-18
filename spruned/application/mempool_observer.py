import time
from spruned.daemon.bitcoin_p2p.p2p_interface import P2PInterface
from spruned.daemon.bitcoin_p2p.utils import get_block_factory
from spruned.repositories.repository import Repository


class MempoolObserver:
    def __init__(self,
                 repository: Repository,
                 p2p_interface: P2PInterface,
                 async_block_factory=get_block_factory()
                 ):
        self.repository = repository
        self.p2p = p2p_interface
        self.block_factory = async_block_factory

    async def on_block_header(self, blockheader: dict):
        if not bool(self.repository.mempool.transactions):
            return
        block = await self.p2p.get_block(blockheader['block_hash'], timeout=15)
        block_object = await self.block_factory.get(block['block_bytes'])
        self.repository.mempool.on_new_block(block_object)
        print(self.repository.mempool.get_mempool_info())

    async def on_transaction_hash(self, connection, item):
        if self.repository.mempool.add_seen(item.data, '{}/{}'.format(connection.hostname, connection.port)):
            await self.p2p.pool.get_from_connection(connection, item)

    async def on_transaction(self, connection, item):
        if self.repository.mempool.add_seen(item['tx'].id(), '{}/{}'.format(connection.hostname, connection.port)):
            transaction = {
                "timestamp": int(time.time()),
                "txid": item["tx"].id(),
                "outpoints": ["{}:{}".format(x.previous_hash, x.previous_index) for x in item["tx"].txs_in],
                "bytes": item['tx'].as_bin()
            }
            transaction["size"] = len(transaction["bytes"])
            self.repository.mempool.add_transaction(transaction["txid"], transaction)
