from unittest import TestCase
from unittest.mock import Mock, create_autospec, ANY

import asyncio

from pycoin.block import Block
from pycoin.merkle import merkle

from spruned.application.mempool_observer import MempoolObserver
from spruned.daemon.bitcoin_p2p.p2p_connection import P2PConnectionPool
from spruned.daemon.bitcoin_p2p.p2p_interface import P2PInterface
from spruned.repositories.mempool_repository import MempoolRepository
from spruned.repositories.repository import Repository
from test.utils import async_coro, batcher_factory


class TestMempoolObserver(TestCase):
    def setUp(self):
        self.repository = create_autospec(Repository)
        self.mempool_repository = MempoolRepository()
        self.repository.mempool = self.mempool_repository
        self.batcher_factory = Mock()
        self.pool = P2PConnectionPool(batcher=lambda: batcher_factory(self))
        self.connection = Mock(connected=True, score=99)
        self.connection2 = Mock(connected=True, score=99)
        self.pool.connections.append(self.connection)
        self.pool.connections.append(self.connection2)
        self.p2p_interface = P2PInterface(self.pool)
        self.sut = MempoolObserver(self.repository, self.p2p_interface)
        self.loop = asyncio.get_event_loop()

    def test_mempool_observer(self):
        connection = Mock()
        from pycoin.tx.Tx import Tx
        tx = Tx.from_hex(
            '01000000000101112a649fd72656cf572259cb7cb61bd31ccdbdf0944070e73401565affbe629d0100000000ffffffff02608'
            'de2110000000017a914d52b516c1a094462959ed6facebb94429d2cebf487d3135b0b00000000220020701a8d401c84fb13e6'
            'baf169d59684e17abd9fa216c8cc5b9fc63d622ff8c58d0400473044022006b149e0cf031f57fd443bd1210b381e9b1b15094'
            '57ba1f49e48b803696f56e802203d66bd974ad3ac5b7591cc84e706b78d139c61e2bf1995a89c4dc0758984a2b70148304502'
            '2100fe7275d601080e1870517774a3ad6accaa7f8ad144addec3251e98685d4fefad02207792c2b0ed6ab42ed2ba6d12e6bd3'
            '4db8c6f4ac6f15e604f70ea85a735c450b1016952210375e00eb72e29da82b89367947f29ef34afb75e8654f6ea368e0acdfd'
            '92976b7c2103a1b26313f430c4b15bb1fdce663207659d8cac749a0e53d70eff01874496feff2103c96d495bfdd5ba4145e3e'
            '046fee45e84a8a48ad05bd8dbb395c011a32cf9f88053ae00000000'
        )
        self.loop.run_until_complete(self.sut.on_transaction(connection, {'tx': tx}))
        self.assertEqual(tx.w_id(), [x for x in self.mempool_repository.get_txids()][0])
        self.repository.blockchain.get_transactions_by_block_hash.return_value = [], None

        block = Block(1, b'0'*32, merkle_root=merkle([tx.hash()]), timestamp=123456789, difficulty=3000000, nonce=1*137)
        block.txs.append(tx)
        as_bin = block.as_bin()
        Block.from_bin(as_bin)
        block_header = {'block_hash': block.id()}
        self.batcher_factory.add_peer.return_value = async_coro(True)
        self.batcher_factory.inv_item_to_future.return_value = block.as_bin()
        mempool_response = self.mempool_repository.get_raw_mempool(True)

        self.assertEqual(
            {
                '41867301a6cff5c47951aa1a4eef0be910db0cb5f154eaeb469732e1f9b54548': {
                    'size': 381,
                    'fee': 0,
                    'modifiedfee': 0,
                    'time': ANY,
                    'height': 0,
                    'descendantcount': 0,
                    'descendantsize': 0,
                    'descendantfees': 0,
                    'ancestorcount': 0,
                    'ancestorsize': 0,
                    'ancestorfees': 0,
                    'depends': []
                }
            },
            mempool_response
        )
        self.repository.blockchain.save_block.side_effect = lambda a: {'block_object': Block.from_bin(a['block_bytes'])}
        self.repository.blockchain.get_transactions_by_block_hash.return_value = [], None
        self.loop.run_until_complete(self.sut.on_block_header(block_header))
        self.assertEqual(self.mempool_repository.get_raw_mempool(True), {})
        self.assertEqual([x for x in self.mempool_repository.get_txids()], [])
