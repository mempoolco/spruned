#### Raspberry Pi Installation & Usage

Installation on my Raspberry Pi B was a bit tricky. <br />
Equipped with Raspbian 8.0 and up-to-date, there is lack of Python 3.5.3 and updated LevelDB version, so you have
to install them manually.<br />
<br />
into scripts/ folder there are some scripts available

First, clone Github Repository: <br /><br />

```
guido@flatline:~/.spruned$ git clone https://github.com/gdassori/spruned.git
```
<br />

Then, 

- Ensure you have Python >= 3.5.3. <br />You can use scripts/install_python3.5.sh to install Python3.5<br /><br />
- Ensure you have LevelDB 1.20 libraries. <br />You can use scripts/install_leveldb.sh to install LevelDB 1.20<br /><br />
- Run setup.sh to install all the dependencies.<br /><br />
- Obtain bitcoin-cli from https://bitcoin.org/en/download<br /><br/>

Then,

```
guido@flatline:~/.spruned$ spruned & >/dev/null 2>&1

guido@flatline:~/.spruned$ bitcoin-cli getblockchaininfo

{
  "chain": "main",
  "warning": "spruned v0.0.1. emulating bitcoind v0.16",
  "blocks": 516476,
  "headers": 516476,
  "bestblockhash": "00000000000000000006af3bd11392060bb5448ae8909cf00ccdfc612360c697",
  "difficulty": null,
  "chainwork": null,
  "mediantime": 1522776544,
  "verificationprogress": 100,
  "pruned": false
}
 
```

Done! <br /><br />

As in any other installation, a directory is created:


```
guido@flatline:~/.spruned$ ls -lnsa
total 16
4 drwxrwxr-x  3 1000 1000 4096 mar 28 02:04 .
4 drwxr-xr-x 49 1000 1000 4096 apr  3 14:52 ..
4 -rw-rw-r--  1 1000 1000 2250 apr  3 19:39 spruned.log
4 drwxrwxr-x  3 1000 1000 4096 apr  3 19:28 storage

guido@flatline:~/.spruned$ ls -lnsa storage/
total 132200
     4 drwxrwxr-x 3 1000 1000      4096 apr  3 19:28 .
     4 drwxrwxr-x 3 1000 1000      4096 mar 28 02:04 ..
     4 drwxr-xr-x 2 1000 1000      4096 apr  3 19:20 database.ldb
132188 -rw-r--r-- 1 1000 1000 135356416 apr  3 19:28 headers.db

```
<br /><br />

Do you need the block 10000 ? 

```
guido@flatline:~$ bitcoin-cli getblock `bitcoin-cli getblockhash 10000`

{
  "hash": "0000000099c744455f58e6c6e98b671e1bf7f37346bfd4cf5d0274ad8ee660cb",
  "height": 10000,
  "version": 1,
  "versionHex": "Not Implemented Yet",
  "merkleroot": "9c397f783042029888ec02f0a461cfa2cc8e3c7897f476e338720a2a86731c60",
  "time": 1238988213,
  "mediantime": 1238988213,
  "nonce": 2145410362,
  "bits": 486604799,
  "difficulty": "Not Implemented Yet",
  "chainwork": "Not Implemented Yet",
  "previousblockhash": "00000000fbc97cc6c599ce9c24dd4a2243e2bfd518eda56e1d5e47d29e29c3a7",
  "nextblockhash": "00000000f01df1dbc52bce6d8d31167a8fef76f1a8eb67897469cf92205e806b",
  "tx": [
    "9c397f783042029888ec02f0a461cfa2cc8e3c7897f476e338720a2a86731c60"
  ]
}

```

<br /> 
Or in raw format ?
<br /><br />

```
guido@flatline:~$ bitcoin-cli getblock `bitcoin-cli getblockhash 10000` 0

01000000a7c3299ed2475e1d6ea5ed18d5bfe243224add249cce99c5c67cc9fb00000000601c73862a0a72
38e376f497783c8ecca2cf61a4f002ec8898024230787f399cb575d949ffff001d3a5de07f010100000001
0000000000000000000000000000000000000000000000000000000000000000ffffffff0804ffff001d02
6f03ffffffff0100f2052a010000004341042f462d3245d2f3a015f7f9505f763ee1080cab36191d07ae9e
6509f71bb68818719e6fb41c019bf48ae11c45b024d476e19b6963103ce8647fc15fee513b15c7ac000000
00
```

<br /><br />
With all the block headers and the last 200 blocks saved locally, less than 500 megabytes.

```
guido@flatline:~/.spruned$ du -d 1

385720	./storage
385868	.

```
<br /><br />
Oh! forgot to say:

```bash

guido@flatline:~/.spruned$ cat ~/.bitcoin/bitcoin.conf 
rpcuser=rpcuser
rpcpassword=password

```

And you may want to check spruned/settings.py

<br /><br />
Now, transactions:

```
guido@flatline:~$ bitcoin-cli getrawtransaction 5b867eab485a3509ba2aea7dc0d7404a785a16c96fac258836aabc02d5f21a68

0100000001f23fecdc5fb720f008d52441bd6f8abbd87acc29740e366c576f443290514ffa050000006a47304402205f7bf9ab7f72882bd46878edaf457699b54aff8343d0d595f43d3021625a29f302207ec0aef71a651b382ddf4803836ae0e94ea9b8ac77d01b5b1ef7c76cf877d8320121037eb0a1e4fa2bc48eeea5d0978af7d8df5e6d0df8a2137e0b7dbde979a2f90276ffffffff0269cf0800000000001976a914ef6f80ff0e32d248a4146b0f95ff4316f5b7a82188ace0fd1c000000000017a91403ecefc1f77da8ff129297d00c4c4e5060307fb18700000000
```

<br /><br />
And what about a random unspent I check ?

```
guido@flatline:~$ bitcoin-cli gettxout 5b867eab485a3509ba2aea7dc0d7404a785a16c96fac258836aabc02d5f21a68 0

{
  "bestblock": "0000000000000000004a78e90f5902cf32427bb61a16550fbe688fc862fa3a94",
  "confirmations": 0,
  "value": 0.00577385,
  "scriptPubKey": {
    "asm": null,
    "hex": "76a914ef6f80ff0e32d248a4146b0f95ff4316f5b7a82188ac",
    "reqSigs": null,
    "type": "",
    "addresses": [
    ]
  }
}

```
