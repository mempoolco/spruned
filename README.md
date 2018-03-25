## sPRUNED
#### A Bitcoin lightweight client that can fetch any block or transaction

<p>sPRUNED emulate the bitcoind rpc server as a full node of BTC mainnet</p>

[![travis](https://travis-ci.org/gdassori/spruned.svg?branch=master)](https://travis-ci.org/gdassori/spruned)
[![coveralls](https://coveralls.io/repos/github/gdassori/spruned/badge.svg)](https://coveralls.io/github/gdassori/spruned)

#### Usage
w.i.p., not usable yet. follow the project and come back later!

However, this is how things are going to be:
```
$ spruned --daemon
$ bitcoin-cli getblockchaininfo
```

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
- <s>gettxout</s>
- <s>sendrawtransaction</s>


#### Requirements
- An internet connection
- **~200mb of disk space :-)**
- Python 3.6


#### How sPRUNED works:
It uses an hybrid the P2P bitcoin network, and the electrum network, to gather and verify the informations you need.<br />
Project is **w.i.p.** and at this moment some functionalities (gettxout and in some way getrawtransaction) are not full functional.
<br />
<br />
Fetched data is cached on a the local file system.<br />

 
#### Crypto-verified
Headers are locally stored, fetched from the electrum network and verified since the Genesis block.  

#### How to lose money: 
- Everything is **as-is** and **pre-alpha**.
- Supports mainnet only (I don't often test my stuff, but when I do it... no, kidding, tests will come)
