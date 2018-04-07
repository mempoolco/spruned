## sPRUNED
#### A Bitcoin lightweight client that can fetch any block or transaction

[![travis](https://travis-ci.org/gdassori/spruned.svg?branch=master)](https://travis-ci.org/gdassori/spruned)
[![coveralls](https://coveralls.io/repos/github/gdassori/spruned/badge.svg)](https://coveralls.io/github/gdassori/spruned)

#### What's this?

<p>sPRUNED is a bitcoin client for light systems. <br />
256mb ram & 500mb hdd should be fairly enough to keep it up & running.
<br /><br/>

At this very moment it supports only bitcoin mainnet. Testnet support will come soon before beta release.<br /><br />
It's a replacement for bitcoind on lightweight systems (It's proven to work on a Raspberry Zero, along with CLightning), it provides an interface for bitcoin-cli. <br />
<br />

#### How it works?

spruned downloads and store the bitcoin blocks on demand, when you need them, directly from the Peer2Peer Bitcoin Network.<br/>
there's a "pruning" functionality emulation, to keep the last ~200 (default settings) blocks on the local storage, because 
fetch blocks may require also up to 10 seconds with slow connections, and this "bootstrap mode" reduces latencies on usage.<br />

You can use bitcoin-cli, or any other RPC client, as if you had bitcoind up & running.<br />
For the transactions related APIs and utxo tracking, spruned uses the electrum network.

#### Dependencies

spruned works with Python >= 3.5.3. Right now it should work only on Linux systems.<br />
<br />
It make intensive usage of connectrum, pybitcointools and pycoinnet libraries. Thanks to mantainers & contributors! <br />

#### Usage
I hope code is self explaining enough, if you're familiar with asyncio.<br />

For the non-developers: a fungible entry point is not ready yet.<br />
However, this is how things are going to be:
```
$ spruned --daemon
$ bitcoin-cli getblockchaininfo
```
Pretty easy.
<br /><br />

##### Emulated APIs as in bitcoind 0.16:

- estimatefee
- estimatesmartfee [ it's an alias to estimatefee ]
- getbestblockhash
- getblock [mode 0 and mode 1]
- getblockchaininfo
- getblockcount
- getblockhash
- getblockheader [ verbose \ non verbose ]
- <s>getmempoolinfo</s>
- <s>getrawmempool</s> [ verbose \ non verbose]
- getrawtransaction [ non verbose only ]
- gettxout
- <s>sendrawtransaction</s>


#### Requirements
- An internet connection
- **less than 500mb of disk space :-)**
- Python >= 3.5.2


#### Limitations

- May reduce privacy: if you have the entire blockchain on your own, you have to tell no one what you're looking for.
- Not fast as a full node: internet download is slower than a read from disk.
- Doesn't relay and partecipate to the network (this may change).
- Very unstable!


#### Future developments
 
- Pluggable currencies specs
- Full Tor support
- Mempool emulation
- Zeromq emulation
- Maintenance UI