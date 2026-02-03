# CLAUDE.md - AI Assistant Guide for spruned

## Project Overview

**spruned** is a lightweight Bitcoin pseudonode client that emulates a full `bitcoind` node via JSON-RPC API without storing the entire blockchain. It's designed for resource-constrained systems (128MB RAM, 500MB disk).

- **Version**: 0.0.10
- **Emulates**: bitcoind v0.16
- **Language**: Python 3.5.2+
- **License**: MIT

### Key Features
- Bitcoin RPC API compatible with `bitcoin-cli`
- Supports Bitcoin Mainnet, Testnet, and Regtest
- Backs Lightning Network implementations (c-lightning, LND)
- Downloads blocks on-demand from P2P network
- Uses Electrum network for transaction/UTXO queries

## Directory Structure

```
spruned/
├── spruned/                     # Main package
│   ├── app.py                   # CLI entry point & argument parser
│   ├── main.py                  # Async main event loop
│   ├── builder.py               # Component factory/builder
│   ├── settings.py              # Configuration constants
│   │
│   ├── application/             # Core application logic
│   │   ├── context.py           # Global context & config
│   │   ├── jsonrpc_server.py    # JSON-RPC HTTP server
│   │   ├── spruned_vo_service.py # RPC command handlers
│   │   ├── database.py          # SQLite & LevelDB setup
│   │   ├── cache.py             # Block cache management
│   │   ├── logging_factory.py   # Module-specific loggers
│   │   ├── migrations/          # Database migrations
│   │   └── networks/            # Network configurations
│   │
│   ├── daemon/                  # Network layer
│   │   ├── electrod/            # Electrum protocol interface
│   │   ├── bitcoin_p2p/         # Bitcoin P2P interface
│   │   ├── tasks/               # Async reactor tasks
│   │   │   ├── headers_reactor.py
│   │   │   └── blocks_reactor.py
│   │   └── zeromq.py            # ZMQ publisher
│   │
│   ├── repositories/            # Data access layer
│   │   ├── repository.py        # Facade for all repos
│   │   ├── headers_repository.py # SQLite header storage
│   │   ├── blockchain_repository.py # LevelDB block/tx storage
│   │   └── mempool_repository.py # In-memory mempool
│   │
│   └── dependencies/            # Vendored libraries
│       ├── connectrum.py        # Electrum protocol
│       ├── pybitcointools.py    # Bitcoin utilities
│       └── pycoinnet/           # P2P protocol
│
├── test/                        # Test suite
│   ├── test_application/        # Core app tests
│   │   ├── test_jsonrpc/        # RPC endpoint tests
│   │   └── test_repositories/   # Data layer tests
│   ├── test_daemon/             # Network daemon tests
│   │   ├── test_electrod/
│   │   └── test_p2p/
│   └── utils.py                 # Test helpers
│
├── docs/                        # Sphinx documentation
├── scripts/                     # Deployment scripts
├── spruned.py                   # Convenience entry script
├── setup.py                     # Package configuration
└── requirements.txt             # Dependencies
```

## Development Commands

### Setup

```bash
# Install system dependencies
sudo apt-get install libleveldb-dev python3-dev git virtualenv gcc g++

# Create virtual environment
virtualenv -p python3.6 venv
. venv/bin/activate

# Install dependencies
pip install -r requirements.txt
python setup.py install
```

### Running the Application

```bash
# Run directly
python spruned.py --rpcbind 127.0.0.1 --rpcport 8332 --network bitcoin.mainnet

# With debug logging
python spruned.py --debug --network bitcoin.testnet

# View logs
tail -f ~/.spruned/spruned.log
```

### Running Tests

```bash
# Run all tests
TESTING=1 python -m unittest discover

# Run with coverage
coverage run --source=spruned -m unittest discover
coverage report
coverage html  # generates htmlcov/index.html

# Run specific test
python -m unittest test.test_application.test_jsonrpc.test_getblock
```

## Architecture

### Entry Point Flow

```
spruned.py → spruned/app.py:main()
  ├── Parse CLI arguments
  ├── Load config from ~/.spruned/spruned.conf
  ├── Run database migrations
  └── Start main_task() → spruned/main.py
```

### Runtime Components

1. **JSONRPCServer** - aiohttp-based HTTP server for RPC
2. **HeadersReactor** - Syncs block headers from Electrum
3. **BlocksReactor** - Downloads blocks from P2P network
4. **ElectrodInterface** - Connection pool to Electrum servers
5. **P2PInterface** - Connection pool to Bitcoin peers

### Data Flow

```
RPC Request → JSONRPCServer → SprunedVOService
                                    ↓
                    ┌───────────────┼───────────────┐
                    ↓               ↓               ↓
              Repository   ElectrodInterface  P2PInterface
                    ↓               ↓               ↓
            SQLite/LevelDB    Electrum       Bitcoin P2P
```

## Code Conventions

### Async Pattern

All I/O operations use asyncio:

```python
async def method_name(self):
    async with async_timeout.timeout(30):
        await some_async_operation()
```

### Locking Pattern

```python
async def critical_section(self):
    try:
        await self.lock.acquire()
        # Do work
    finally:
        self.lock.release()
```

### Logging

Use module-specific loggers from `logging_factory`:

```python
from spruned.application.logging_factory import Logger

Logger.electrum.info('Connected to %s', server)
Logger.p2p.debug('Received block %s', block_hash)
Logger.jsonrpc.exception('RPC error', exc_info=True)
```

Available loggers: `root`, `repository`, `electrum`, `p2p`, `leveldb`, `mempool`, `bitcoind`, `cache`, `jsonrpc`, `zmq`

### Database Transactions

Use the `@atomic` decorator for SQLite operations:

```python
@atomic
def update_headers(self, headers):
    # Auto-commits on success, rolls back on error
    pass
```

### Testing Pattern

Tests use unittest with mocks and async helpers:

```python
from unittest import TestCase
from unittest.mock import Mock
from test.utils import async_coro

class TestSomething(TestCase):
    def setUp(self):
        self.mock_service = Mock()
        self.loop = asyncio.get_event_loop()

    def test_async_operation(self):
        self.mock_service.method.return_value = async_coro({'result': 'value'})

        async def test():
            result = await self.sut.operation()
            return result

        result = self.loop.run_until_complete(test())
        self.assertEqual(result, expected)
```

## Key Files Reference

| File | Purpose |
|------|---------|
| `spruned/app.py` | CLI entry point, argument parsing |
| `spruned/main.py` | Main async loop, component coordination |
| `spruned/builder.py` | Factory for all major components |
| `spruned/application/jsonrpc_server.py` | RPC server implementation |
| `spruned/application/spruned_vo_service.py` | RPC command handlers |
| `spruned/daemon/tasks/headers_reactor.py` | Header synchronization |
| `spruned/daemon/tasks/blocks_reactor.py` | Block download management |
| `test/utils.py` | Test helper functions (`async_coro`, `MockValidator`) |

## Configuration

### CLI Arguments

Key arguments (see `--help` for full list):
- `--rpcuser`, `--rpcpassword` - RPC authentication
- `--rpcport`, `--rpcbind` - RPC server binding
- `--network` - `bitcoin.mainnet`, `bitcoin.testnet`, `bitcoin.regtest`
- `--datadir` - Data directory (default: `~/.spruned`)
- `--cache-size` - Cache size in MB (default: 50)
- `--keep-blocks` - Number of blocks to keep locally (default: 200)
- `--debug` - Enable debug logging
- `--tor`, `--proxy` - Tor/proxy support

### Config File

Optional config at `~/.spruned/spruned.conf`

### Environment Variables

- `TESTING=1` - Enables test mode (in-memory databases)
- `DEBUG=1` - Enables debug logging

## Supported RPC Commands

```
== Blockchain ==
getbestblockhash, getblock, getblockchaininfo, getblockcount,
getblockhash, getblockheader, gettxout, getmempoolinfo, getrawmempool

== Rawtransactions ==
getrawtransaction, sendrawtransaction

== Util ==
estimatefee, estimatesmartfee, uptime

== Network ==
getpeerinfo, getnetworkinfo

== Wallet ==
validateaddress

== Partially Emulated ==
getchaintxstats, getmininginfo, getnettotals
```

## Common Tasks

### Adding a New RPC Method

1. Add handler in `spruned/application/spruned_vo_service.py`
2. Register in `spruned/application/jsonrpc_server.py`
3. Add tests in `test/test_application/test_jsonrpc/`

### Modifying Network Behavior

- Electrum: `spruned/daemon/electrod/`
- P2P: `spruned/daemon/bitcoin_p2p/`
- Reactors: `spruned/daemon/tasks/`

### Database Changes

1. Add migration in `spruned/application/migrations/`
2. Update version in `blockchain_repository.py`
3. Migrations run automatically on startup

## Dependencies

Core dependencies from `requirements.txt`:
- `aiohttp` - Async HTTP server/client
- `jsonrpcserver` - JSON-RPC 2.0 framework
- `plyvel` - LevelDB bindings
- `pycoin` - Bitcoin protocol encoding
- `pyzmq` - ZeroMQ support
- `sqlalchemy` - SQLite ORM

## Notes for AI Assistants

1. **Always use asyncio** - This is a fully async codebase
2. **Test with mocks** - External services should be mocked in tests
3. **Use appropriate logger** - Don't use print(), use Logger.module
4. **Run tests** - `TESTING=1 python -m unittest discover`
5. **Data directory** - Default is `~/.spruned/`, configurable via `--datadir`
6. **Python version** - Minimum 3.5.2, tested on 3.5.3, 3.6.3, 3.7.2
7. **LevelDB required** - System dependency: `libleveldb-dev`
