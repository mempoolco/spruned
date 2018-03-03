## sPRUNED
#### A Bitcoin full node emulator with a limited set of APIs

<p>sPRUNED emulate the bitcoind rpc server as a full node of BTC mainnet</p>

####Usage

w.i.p., not usable yet. follow\star the project and come back later!

However, this is how things are going to be:
```
$ spruned --daemon
$ bitcoin-cli getblockchaininfo
```

#####Emulated APIs as in bitcoind 0.16:

```
- estimatefee
- getbestblockhash
- getblock [only mode 1 is supported: a json object without transactions data]
- getblockchaininfo
- getblockhash
- getblockheader [verbose \ non verbose]
- getblockheight
- getmempoolinfo
- getrawtransaction [non verbose only]
- sendrawtransaction
```

####Requirements

- An internet connection
- ~200mb of disk space :-)
- Python 3.6 [may work with python 3.5.2, keep in mind I code with 3.6]


####How sPRUNED works:
It uses an hybrid of public services (blockchaininfo, chainso, blocktrail, blockcypher, etc.) and 
the electrum network to gather the informations you need.<br />
Fetched data is cached on a the local file system.<br />
<s>Cached blocks are served to spru-net when sPRUNED P2P mode is enabled.</s><br /> 

####Crypto-verified
<p>
Headers are locally stored, fetched from the electrum network and verified since the Genesis block.<br/>
Transactions [not yet] [will be soon] <s>are</s> crypto-verified with merkle proofs.</p>  

####How to lose money: 

- Everything is **as-is** and **pre-alpha**.
- Supports mainnet only (I don't often test my stuff, but when I do it...)
- To lose your money, be #reckless and use sPRUNED with real money and rely on it! Easy!


###### Out-of-date but maybe still funny:
- (Don't ) [Read MOTIVATIONS](./MOTIVATIONS.md) [old]
- (Don't ) [Read USAGE](./USAGE.md) [old]


**Forgot to say: this README is mendacious, not everything works yet!**