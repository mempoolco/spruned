from spruned import networks
from spruned.application import exceptions
from spruned.application.tools import blockheader_to_blockhash
from spruned.repositories.repository_types import Block, BlockHeader
from . import RepositoryTestCase


class TestChainRepository(RepositoryTestCase):
    async def test_genesis(self, stop_db=True):
        genesis_block = bytes.fromhex(networks.bitcoin.regtest['genesis_block'])
        initialize_response = await self.sut.initialize(
            Block(
                data=genesis_block,
                hash=blockheader_to_blockhash(genesis_block),
                height=0
            )
        )
        self.assertEqual(initialize_response.data, genesis_block)
        self.assertEqual(initialize_response.height, 0)
        self.assertEqual(initialize_response.hash, blockheader_to_blockhash(genesis_block))
        get_block_response = await self.sut.get_block_hash(0)
        self.assertEqual(get_block_response, initialize_response.hash)
        get_best_height_response = await self.sut.get_best_height()
        self.assertEqual(get_best_height_response, 0)
        get_header_response = await self.sut.get_header(
            bytes.fromhex(blockheader_to_blockhash(networks.bitcoin.regtest['genesis_block']))
        )
        self.header_0 = BlockHeader(
            data=b'\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                 b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00;\xa3\xed\xfdz{\x12\xb2z\xc7,>gv\x8fa\x7f'
                 b'\xc8\x1b\xc3\x88\x8aQ2:\x9f\xb8\xaaK\x1e^J\xda\xe5IM\xff\xff\x7f \x02\x00\x00\x00',
            height=0,
            hash=b'\x0f\x91\x88\xf1<\xb7\xb2\xc7\x1f*3^:O\xc3(\xbf[\xebC`\x12\xaf\xcaY\x0b\x1a\x11Fn"\x06'
        )
        self.assertEqual(len(self.header_0.data), 80)
        self.assertEqual(self.header_0, get_header_response)
        self._init_leveldb()
        initialize_response_2 = await self.sut.initialize(
            Block(
                data=genesis_block,
                hash=blockheader_to_blockhash(genesis_block),
                height=0
            )
        )
        self.assertEqual(initialize_response_2, initialize_response)
        if stop_db:
            await self.diskdb.stop()

    async def test_save_headers(self):
        headers = [
            BlockHeader(
                data=b'\x00\x00\x00 \x06"nF\x11\x1a\x0bY\xca\xaf\x12`C\xeb[\xbf(\xc3O:^3*\x1f\xc7\xb2\xb7<\xf1'
                     b'\x88\x91\x0f\xb3D\x97\xc7Ca\xc5\xa0\xcb*b\x93V\x05\xb8\x88K\x8d\xc1MY\xe4\xd9\x13l'
                     b'\xc9WK@\x85\xae\xdf\x8b\xb0\x01\\\xff\xff\x7f \x00\x00\x00\x00',
                height=1,
                hash=b'>\x1cG|\xc6\x9d\x0275$\xc7\x07\xa6\xba\xfc=F\x04\x07\xea\x86\xd1w\xc5\x17\xdb\r\xe3\xb2,p\xfd'
            ),
            BlockHeader(
                data=b'\x00\x00\x00 \xfdp,\xb2\xe3\r\xdb\x17\xc5w\xd1\x86\xea\x07\x04F=\xfc\xba\xa6\x07\xc7$57'
                     b'\x02\x9d\xc6|G\x1c>\x08\xba\x1ey\xea\xb2z\x1e\xfb\x8e\xa7\x12Z\x95\x00\x1c\x95\xad\x12!D'
                     b'\xb8u;\x96<\xf7\xa84\x87\xf9/\x8c\xb0\x01\\\xff\xff\x7f \x01\x00\x00\x00',
                height=2,
                hash=b'Ee\xc6\x05\xdb\xc2\xf3\x02-7\xbf\x93\x9d\xcb\x014BF\xe5aL\x01\x1b\xeeBuIn\xa9k\xa8\x82'
            ), BlockHeader(
                data=b'\x00\x00\x00 \x82\xa8k\xa9nIuB\xee\x1b\x01La\xe5FB4\x01\xcb\x9d\x93\xbf7-\x02\xf3\xc2'
                     b'\xdb\x05\xc6eEx\x8d\xdaj\xde\x00!#\x1d\xeeZ\xcfi\x89\x85\x9eIb\xab(0\xc9\x82\xe5\x81\xf4x'
                     b'\xb4\x97%\x87\xb1\x8c\xb0\x01\\\xff\xff\x7f \x01\x00\x00\x00',
                height=3,
                hash=b"D\xc3\x155\xe0y\xa6Q\xf9>\x19B\x15\xe1\xcc6\x85'&l\xe2\xf5\xf2\x14O\xa4\xd57\xe19n;"
            )
        ]
        await self.test_genesis(stop_db=False)
        saved_headers = await self.sut.save_headers(headers)
        self.assertEqual(headers, saved_headers)
        self.assertEqual(3, await self.sut.get_best_height())

        headers.insert(0, await self.sut.get_header(
            bytes.fromhex(blockheader_to_blockhash(networks.bitcoin.regtest['genesis_block']))
        ))
        for height in range(0, 4):
            block_hash_response = await self.sut.get_block_hash(height)
            self.assertEqual(headers[height].hash, block_hash_response)
            get_header_response = await self.sut.get_header(block_hash_response)
            self.assertEqual(headers[height].hash, get_header_response.hash)
            self.assertEqual(headers[height], get_header_response)
        headers_batch = await self.sut.get_headers(headers[0].hash)
        self.assertEqual(headers_batch, headers)

    async def test_repo_reinitialize(self):
        await self.test_genesis(stop_db=False)
        self._init_sut()
        best_header = await self.sut.get_best_header()
        self.assertEqual(best_header, self.header_0)
        genesis_block = bytes.fromhex(networks.bitcoin.regtest['genesis_block'])
        await self.sut.initialize(
            Block(
                data=genesis_block,
                hash=blockheader_to_blockhash(genesis_block),
                height=0
            )
        )

    async def test_get_best_block_hash(self):
        await self.test_save_headers()
        best_block_hash = await self.sut.get_best_block_hash()
        self.assertEqual(
            b"D\xc3\x155\xe0y\xa6Q\xf9>\x19B\x15\xe1\xcc6\x85'&l\xe2\xf5\xf2\x14O\xa4\xd57\xe19n;",
            best_block_hash
        )
        multiple_blocks_hash = await self.sut.get_block_hashes_in_range(0, 2)
        self.assertEqual(
            multiple_blocks_hash,
            [
                b'\x0f\x91\x88\xf1<\xb7\xb2\xc7\x1f*3^:O\xc3(\xbf[\xebC`\x12\xaf\xcaY\x0b\x1a\x11Fn"\x06',
                b'>\x1cG|\xc6\x9d\x0275$\xc7\x07\xa6\xba\xfc=F\x04\x07\xea\x86\xd1w\xc5\x17\xdb\r\xe3\xb2,p\xfd',
                b'Ee\xc6\x05\xdb\xc2\xf3\x02-7\xbf\x93\x9d\xcb\x014BF\xe5aL\x01\x1b\xeeBuIn\xa9k\xa8\x82'
            ]
        )

    async def test_save_block(self):
        raw_blocks = [
            '0000002006226e46111a0b59caaf126043eb5bbf28c34f3a5e332a1fc7b2b73cf188910fb34497c74361c5a0cb2a62935'
            '605b8884b8dc14d59e4d9136cc9574b4085aedf8bb0015cffff7f20000000000102000000000101000000000000000000'
            '0000000000000000000000000000000000000000000000ffffffff03510101ffffffff0200f2052a010000002321026c3'
            'bc1a4f35bc33130187b147594097c79062e9eb9747643b346495e98335f47ac0000000000000000266a24aa21a9ede2f6'
            '1c3f71d1defd3fa999dfa36953755c690689799962b48bebd836974e8cf90120000000000000000000000000000000000'
            '000000000000000000000000000000000000000',
            '00000020fd702cb2e30ddb17c577d186ea0704463dfcbaa607c7243537029dc67c471c3e08ba1e79eab27a1efb8ea7125'
            'a95001c95ad122144b8753b963cf7a83487f92f8cb0015cffff7f20010000000102000000000101000000000000000000'
            '0000000000000000000000000000000000000000000000ffffffff03520101ffffffff0200f2052a010000002321026c3'
            'bc1a4f35bc33130187b147594097c79062e9eb9747643b346495e98335f47ac0000000000000000266a24aa21a9ede2f6'
            '1c3f71d1defd3fa999dfa36953755c690689799962b48bebd836974e8cf90120000000000000000000000000000000000'
            '000000000000000000000000000000000000000',
            '0000002082a86ba96e497542ee1b014c61e546423401cb9d93bf372d02f3c2db05c66545788dda6ade0021231dee5acf6'
            '989859e4962ab2830c982e581f478b4972587b18cb0015cffff7f20010000000102000000000101000000000000000000'
            '0000000000000000000000000000000000000000000000ffffffff03530101ffffffff0200f2052a010000002321026c3'
            'bc1a4f35bc33130187b147594097c79062e9eb9747643b346495e98335f47ac0000000000000000266a24aa21a9ede2f6'
            '1c3f71d1defd3fa999dfa36953755c690689799962b48bebd836974e8cf90120000000000000000000000000000000000'
            '000000000000000000000000000000000000000'
        ]
        blocks = [
            Block(
                hash=blockheader_to_blockhash(bytes.fromhex(block)),
                data=bytes.fromhex(block),
                height=height
            ) for height, block in enumerate(raw_blocks, 1)
        ]
        await self.test_save_headers()
        for block in blocks:
            await self.sut.save_block(block)
        for block in blocks:
            fetched = await self.sut.get_block(block.hash)
            self.assertEqual(block.data, fetched.data)
            self.assertEqual(block.height, fetched.height)
            self.assertEqual(block.hash, fetched.hash)
            self.assertEqual(block.header, fetched.header)

    async def test_save_more_blocks(self):
        await self.test_save_block()
        raw_blocks = [
            '000000203b6e39e137d5a44f14f2f5e26c26278536cce11542193ef951a679e03515c3447b875f08dc37ef8373b415a7b'
            '9daa1babe27f065576463bd8f1155386cb2e7048db0015cffff7f20000000000102000000000101000000000000000000'
            '0000000000000000000000000000000000000000000000ffffffff03540101ffffffff0200f2052a010000002321026c3'
            'bc1a4f35bc33130187b147594097c79062e9eb9747643b346495e98335f47ac0000000000000000266a24aa21a9ede2f6'
            '1c3f71d1defd3fa999dfa36953755c690689799962b48bebd836974e8cf90120000000000000000000000000000000000'
            '000000000000000000000000000000000000000',
            '00000020a0722a70266b39e04c3fbe9bac130ac96d0304506bacd7e6a59807c21391557c31fe14f9b673d3a6841342167'
            '8f42810219a2881312ba3c45eac64c403a38a848db0015cffff7f20010000000102000000000101000000000000000000'
            '0000000000000000000000000000000000000000000000ffffffff03550101ffffffff0200f2052a010000002321026c3'
            'bc1a4f35bc33130187b147594097c79062e9eb9747643b346495e98335f47ac0000000000000000266a24aa21a9ede2f6'
            '1c3f71d1defd3fa999dfa36953755c690689799962b48bebd836974e8cf90120000000000000000000000000000000000'
            '000000000000000000000000000000000000000'
        ]
        blocks = [
            Block(
                hash=blockheader_to_blockhash(bytes.fromhex(block)),
                data=bytes.fromhex(block),
                height=height
            ) for height, block in enumerate(raw_blocks, 4)
        ]
        with self.assertRaises(exceptions.DatabaseInconsistencyException):
            await self.sut.save_block(blocks[0])
        await self.sut.save_headers([blocks[0].header, blocks[1].header])
        await self.sut.save_blocks(blocks)
        self.assertEqual(blocks[-1].header, await self.sut.get_best_header())
        prev_block_hash = await self.sut.get_block_hash(blocks[-1].height)
        h = 5
        while prev_block_hash:
            block = await self.sut.get_block(prev_block_hash)
            self.assertEqual(block.height, h)
            h -= 1
            if block.header.prev_block_hash == bytes.fromhex('00'*32):
                break
            prev_block_hash = block.header.prev_block_hash
