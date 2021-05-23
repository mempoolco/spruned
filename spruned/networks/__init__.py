from . import bitcoin as _bitcoin
bitcoin = _bitcoin

rules = {
    'bitcoin.mainnet': _bitcoin.mainnet,
    'bitcoin.testnet': _bitcoin.testnet,
    'bitcoin.regtest': _bitcoin.regtest
}