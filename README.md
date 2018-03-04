## sPRUNED
#### A Bitcoin full node emulator with a limited set of APIs
<p>sPRUNED emulate the bitcoind rpc server as a full node of BTC mainnet</p>

#### Usage
w.i.p., not usable yet. follow the project and come back later!

However, this is how things are going to be:
```
$ spruned --daemon
$ bitcoin-cli getblockchaininfo
```

##### Emulated APIs as in bitcoind 0.16:

- estimatefee
- estimatesmartfee [it's an alias to estimatefee]
- getbestblockhash
- getblock [mode 1 is supported: a json object with transaction ids]
- getblockchaininfo
- getblockcount
- getblockhash
- getblockheader <s>[verbose \ non verbose]</s>
- <s>getmempoolinfo</s>
- getrawtransaction [non verbose only]
- gettxout
- <s>sendrawtransaction</s>


#### Requirements
- An internet connection
- **~200mb of disk space :-)**
- Python 3.6


#### How sPRUNED works:
It uses an hybrid of public services (blockchaininfo, chainso, blocktrail, blockcypher, etc.) and 
the electrum network to gather and verify the informations you need.<br />
Fetched data is cached on a the local file system.<br />
 
#### Crypto-verified
Headers are locally stored, fetched from the electrum network and verified since the Genesis block.  

#### How to lose money: 
- Everything is **as-is** and **pre-alpha**.
- Supports mainnet only (I don't often test my stuff, but when I do it... no, kidding, tests will come)
