import asyncio
from spruned.daemon import exceptions
from spruned.application.logging_factory import Logger
from spruned.application.tools import async_delayed_task
from spruned.daemon.bitcoin_p2p.p2p_interface import P2PInterface
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
            keep_blocks=200,
            delayed_task=async_delayed_task
    ):
        self.repo = repository
        self.interface = interface
        self.loop = loop or asyncio.get_event_loop()
        self.lock = asyncio.Lock()
        self.delayer = delayed_task
        self._last_processed_block = None
        self._keep_blocks = keep_blocks
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
        urgent = False
        try:
            best_header = self.repo.headers.get_best_header()
            urgent = await self._check_blockchain(best_header)
        except Exception as e:
            urgent = urgent or False
            Logger.p2p.exception('Error on BlocksReactor fallback %s', str(e))
        finally:
            self.loop.create_task(
                self.delayer(self.check(), 0 if urgent else self._fallback_check_interval)
            )

    async def _check_blockchain(self, best_header):
        urgent = False
        try:
            await self.lock.acquire()
            if not self._last_processed_block or \
                    best_header['block_height'] > self._last_processed_block['block_height']:
                urgent = await self._on_blocks_behind_headers(best_header)
            elif best_header['block_height'] < self._last_processed_block['block_height']:
                Logger.p2p.warning('Headers index is behind what this task done. Reset current status')
                self.set_last_processed_block(None)
                urgent = True
                # This will be fixed in the next iteration by on_blocks_behind_header
            else:
                if best_header['block_hash'] != self._last_processed_block['block_hash']:
                    Logger.p2p.warning('There must be a reorg. Reset current status')
                    # This will be fixed in the next iteration by on_blocks_behind_header
                    self.set_last_processed_block(None)
                    urgent = True
        except (
            exceptions.BlocksInconsistencyException
        ):
            Logger.p2p.exception('Exception checkping the blockchain')
            self.set_last_processed_block(None)
            urgent = True
        finally:
            self.lock.release()
            return urgent

    async def _on_blocks_behind_headers(self, best_header):
        if self._last_processed_block and \
                best_header['block_height'] - self._last_processed_block['block_height'] < self._keep_blocks:
            height_to_start = self._last_processed_block['block_height']
            urgent = False
        else:
            height_to_start = best_header['block_height'] - self._keep_blocks
            height_to_start = height_to_start if height_to_start >= 0 else 0
            urgent = True

        headers = self.repo.headers.get_headers_since_height(height_to_start, limit=self._max_per_batch)

        _local_blocks_indexes = {
            k: v for k, v in {
                h['block_hash']: self.repo.blockchain.get_block_index(h['block_hash'])
                for h in headers
            }.items() if v is not None
        }

        _request = [
            x['block_hash'] for x in headers if x['block_hash'] not in _local_blocks_indexes.keys()
        ]
        if _request:
            blocks = await self.interface.get_blocks(*_request)
            urgent = urgent or False
            try:
                sorted_values = sorted(blocks.values(), key=lambda x: x['block_hash'])
                saved_blocks = self.repo.blockchain.save_blocks(*sorted_values)
                last_hash = saved_blocks and saved_blocks[-1]['block_hash']
                Logger.p2p.debug('Saved block %s', saved_blocks)
            except:
                Logger.p2p.warning('Error saving blocks %s', blocks)
                return True
        else:
            urgent = True
            last_hash = headers[-1]['block_hash']

        if last_hash:
            _headers_by_block_hash = {v['block_hash']: v for v in headers}
            self.set_last_processed_block(
                {
                    'block_hash': last_hash,
                    'block_height': _headers_by_block_hash[last_hash]['block_height']
                }
            )
        else:
            urgent = True
        return urgent

    async def on_connected(self):
        self._available = True
        self.loop.create_task(self.check())

    async def start(self, *a, **kw):
        self.interface.add_on_connect_callback(self.on_connected)
        self.loop.create_task(self.interface.start())

    async def bootstrap_blocks(self, *a, **kw):
        while len(self.interface.pool.established_connections) < self.interface.pool.required_connections / 2:
            Logger.p2p.info('Bootstrap: ConnectionPool not ready yet')
            await asyncio.sleep(30)
        Logger.p2p.info('Bootstrap: Downloading %s blocks', self._keep_blocks)
        try:
            await self.lock.acquire()
            best_header = self.repo.headers.get_best_header()
            headers = self.repo.headers.get_headers_since_height(best_header['block_height'] - self._keep_blocks)
            missing_blocks = []
            for blockheader in headers:
                if not self.repo.blockchain.get_block_index(blockheader['block_hash']):
                    missing_blocks.append(blockheader['block_hash'])
            i = 0
            while 1:
                i += 1
                if len(self.interface.pool.established_connections) - len(self.interface.pool._busy_peers) \
                        < self.interface.pool.required_connections / 2:
                    Logger.p2p.debug('Missing peers. Waiting.')
                    await asyncio.sleep(20)
                    continue

                status = float(100) / self._keep_blocks * (len(headers) - len(missing_blocks))
                status = status if status <= 100 else 100
                self.interface.set_bootstrap_status(status)
                missing_blocks = missing_blocks[::-1]
                blocks_per_round = min([int(len(self.interface.pool.established_connections)*0.5), len(missing_blocks)])
                _blocks = missing_blocks and [missing_blocks[i] for i in range(0, blocks_per_round)] or []
                if not _blocks:
                    Logger.p2p.info('Bootstrap: No blocks to fetch.')
                    break
                not i and Logger.p2p.info('Bootstrap: Fetching %s blocks', len(_blocks))

                async def save_block(blockhash):
                    block = (await asyncio.gather(
                        self.interface.get_block(blockhash, peers=1, timeout=10),
                        return_exceptions=True
                    ))[0]
                    if block and isinstance(block, dict):
                        missing_blocks.remove(block['block_hash'])
                        Logger.p2p.info(
                            'Bootstrap: saved block %s (%s/%s)',
                            block['block_hash'],
                            self._keep_blocks - len(missing_blocks),
                            self._keep_blocks
                        )
                        self.repo.blockchain.save_block(block)
                    else:
                        Logger.p2p.debug('Failed downloading block %s, retrying', blockhash)

                futures = [save_block(blockhash) for blockhash in _blocks]
                await asyncio.gather(*futures, return_exceptions=True)
        finally:
            self.lock.release()
