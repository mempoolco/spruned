import asyncio

from pycoin.block import Block

from spruned.application.database import ldb_batch
from spruned.daemon import exceptions
from spruned.application.logging_factory import Logger
from spruned.application.tools import async_delayed_task
from spruned.daemon.p2p import P2PInterface
from spruned.repositories.repository import Repository


class BlocksReactor:
    """
    This reactor keeps non-pruned blocks aligned to the best height.
    """
    def __init__(
            self,
            repository: Repository,
            interface: P2PInterface,
            loop=asyncio.get_event_loop(),
            prune=200,
            delayed_task=async_delayed_task
    ):
        self.repo = repository
        self.interface = interface
        self.loop = loop or asyncio.get_event_loop()
        self.lock = asyncio.Lock()
        self.delayer = delayed_task
        self._last_processed_block = None
        self._prune = prune
        self._max_per_batch = 10
        self._available = False
        self._fallback_check_interval = 30

    def set_last_processed_block(self, last):
        if last != self._last_processed_block:
            self._last_processed_block = last
            Logger.p2p.info(
                'Last processed block: %s (%s)',
                self._last_processed_block and self._last_processed_block['block_height'],
                self._last_processed_block and self._last_processed_block['block_hash'],
            )

    def on_header(self, best_header):
        Logger.p2p.debug('BlocksReactor.on_header: %s', best_header)
        self.loop.create_task(self._check_blockchain(best_header))

    async def check(self):
        try:
            best_header = self.repo.headers.get_best_header()
            await self._check_blockchain(best_header)
            self.loop.create_task(self._fallback_check_interval)
        except Exception as e:
            Logger.p2p.exception('Error on BlocksReactor fallback %s', str(e))

    async def _check_blockchain(self, best_header):
        try:
            await self.lock.acquire()
            if not self._last_processed_block:
                # The bootstrap task must but ran
                return
            if best_header['block_height'] > self._last_processed_block['block_height']:
                await self._on_blocks_behind_headers(best_header)
            elif best_header['block_height'] < self._last_processed_block['block_height']:
                Logger.p2p.warning('Headers index is behind what this task done.')
                pass  # We do nothing. It's some sort of headers reactor issue.
            else:
                if best_header['block_hash'] != self._last_processed_block['block_hash']:
                    raise exceptions.BlocksInconsistencyException
        except (
            exceptions.BlocksInconsistencyException
        ):
            Logger.p2p.exception('Exception checkping the blockchain')
            return
        finally:
            self.lock.release()

    async def _on_blocks_behind_headers(self, best_header):
        if best_header['block_height'] - self._last_processed_block['block_height'] < self._prune:
            height_to_start = self._last_processed_block['block_height']
        else:
            height_to_start = best_header['block_height'] - self._prune
            height_to_start = height_to_start if height_to_start >= 0 else 0

        headers = self.repo.headers.get_headers_since_height(height_to_start, limit=self._max_per_batch)
        _local_blocks = {h['block_hash']: self.repo.blockchain.get_block(h['block_hash'], with_transactions=False) for h in headers}
        _local_hblocks = {k: v for k, v in _local_blocks.items() if v is not None}
        _request = [x['block_hash'] for x in headers if x['block_hash'] not in _local_hblocks]
        blocks = _request and await self.interface.get_blocks(*_request)
        _hheaders = {v['block_hash']: v for v in headers}
        if blocks:
            try:
                saved_blocks = self.repo.blockchain.save_blocks(*blocks.values())
                Logger.p2p.debug('Saved block %s', saved_blocks)
            except:
                Logger.p2p.exception('Error saving blocks %s', blocks)
                return
        else:
            saved_blocks = [_local_hblocks[headers[-1]['block_hash']]]

        saved_blocks and self.set_last_processed_block(
                {
                    'block_hash': saved_blocks[-1]['block_hash'],
                    'block_height': _hheaders[saved_blocks[-1]['block_hash']]['block_height']
                }
            )
        return

    async def _on_headers_behind_blocks(self, best_header):
        try:
            self.repo.blockchain.get_block(best_header['blockhash'])
        except:
            Logger.p2p.exception('Error fetching block in headers_behind_blocks behaviour: %s', best_header)
            raise exceptions.BlocksInconsistencyException

    async def on_connected(self):
        self._available = True
        self.loop.create_task(self.check())

    async def start(self):
        self.interface.add_on_connect_callback(self.on_connected)
        self.loop.create_task(self.interface.start())

    @ldb_batch
    async def bootstrap_blocks(self):
        while len(self.interface.pool.established_connections) < self.interface.pool.required_connections:
            Logger.p2p.debug('Bootstrap: ConnectionPool not ready yet')
            await asyncio.sleep(5)
        try:
            await self.lock.acquire()
            best_header = self.repo.headers.get_best_header()
            headers = self.repo.headers.get_headers_since_height(best_header['block_height'] - self._prune)
            missing_blocks = []
            for blockheader in headers:
                if not self.repo.blockchain.get_block(blockheader['block_hash'], with_transactions=False):
                    missing_blocks.append(blockheader['block_hash'])
            while 1:
                status = float(100) / self._prune * (len(headers) - len(missing_blocks))
                status = status if status <= 100 else 100
                self.interface.set_bootstrap_status(status)
                missing_blocks = missing_blocks[::-1]
                _blocks = [
                    missing_blocks.pop() for _ in
                    range(0, int(len(self.interface.pool.established_connections)*0.75))
                    if missing_blocks
                ]
                if not _blocks:
                    Logger.p2p.debug('Bootstrap: No blocks to fetch.')
                    break
                Logger.p2p.debug('Bootstrap: Fetching %s blocks', len(_blocks))
                futures = [self.interface.get_block(blockhash, peers=1, timeout=10) for blockhash in _blocks]
                data = await asyncio.gather(*futures, return_exceptions=True)
                for i, d in enumerate(data):
                    if isinstance(d, dict):
                        Logger.p2p.debug('Bootstrap: saved block %s', d['block_hash'])
                        self.repo.blockchain.save_block(d)
                    else:
                        Logger.p2p.debug('Bootstrap: enqueuing block %s', _blocks[i])
                        missing_blocks.insert(0, _blocks[i])
        finally:
            self.lock.release()
