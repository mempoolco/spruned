## sPRUNED
#### A Bitcoin lightweight client that can fetch any block or transaction

[![travis](https://travis-ci.org/gdassori/spruned.svg?branch=master)](https://travis-ci.org/gdassori/spruned)
[![coveralls](https://coveralls.io/repos/github/gdassori/spruned/badge.svg)](https://coveralls.io/github/gdassori/spruned)

#### What's this?

<p>sPRUNED is a bitcoin client for light systems. <br />
256mb ram & 500mb hdd should be fairly enough to keep it up & running.
<br />

A lightweight bitcoin client, at this very moment it supports only bitcoin mainnet.
Testnet support will come soon before beta release.<br /><br />
So, run spruned on your low end system and you have the APIs listed below as you have a 200gigs Bitcoind installation.
<br /><br />

#### How it works?

spruned downloads and store the bitcoin blocks on demand, when you need them, directly from the Peer2Peer Bitcoin Network.<br/>
There's a "pruning" functionality emulation, to keep the last ~200 (default settings) blocks already saved, because 
fetch blocks may require also up to 10 seconds with slow connections, and this "bootstrap mode" reduces latencies on usage.<br />

You can use bitcoin-cli, or any other RPC client, as if you had bitcoind up & running.<br /><br />
For the transactions related APIs and utxo tracking, spruned uses the electrum network.

#### Documentation

* [Installation and usage on Raspberry Pi B (1 Core - 512 MB)](https://github.com/gdassori/spruned/tree/master/docs/RASPBERRY.md)

#### Dependencies

spruned works with Python 3.5.2 and Python 3.6, as it uses asyncio. atm it should work only on Linux systems.<br />
<br />
It make intensive usage of connectrum, pybitcointools and pycoinnet libraries. Thanks to mantainers & contributors! <br />
Especially at this stage of development (but it would be better always), it is recommended to use virtualenv to run spruned

#### Usage.
Code should be pretty self explaining if you're familiar with asyncio.<br />
**For the non-developers:** a fungible entry point is **not ready** yet.<br />

However, this is how things are going to be:
```
$ spruned --daemon
$ bitcoin-cli getblockchaininfo
```
Pretty easy.
<br /><br />

##### Emulated APIs as in bitcoind 0.16:
```
- estimatefee
- estimatesmartfee
- getbestblockhash
- getblock [mode 0 and mode 1]
- getblockchaininfo
- getblockcount
- getblockhash
- getblockheader [ verbose \ non verbose ]
- getrawtransaction [ non verbose only ]
- gettxout
```

##### Work in progress:

```
- sendrawtransaction
- getrawtransaction [ verbose ]
- getmempoolinfo
- getrawmempool
```


#### Requirements
- An internet connection
- **less than 500mb of disk space :-)**
- Python >= 3.5.3


#### Limitations

- May reduce privacy: if you have the entire blockchain you don't have to tell no one what you're going to search.
- Not fast as a full node: internet download is slower than a read from disk.
- Doesn't relay and partecipate to the network (this may change).


#### Future development
 
- Pluggable currencies specs
- Full Tor support
- Mempool emulation
- Zeromq emulation
- Maintenance UI
