Overview
========

Motivations
-----------

In the past I wrote a couple of POC, like ChainDNS, Gangsta, Notarium and others. All of them needed a full node.
And so I set up a full node everytime.
Then I needed a small explorer, and I set up a full node to back ABE.
Finally, Clightning went out, and obviously it needs a full node. And I set up another full node.
However, with the growing of the Bitcoin Blockchain and the spread of low end boxes, setting up a full node may be tricky.


How it works
------------

spruned enable a reduced set of the bitcoind RPC API by querying the blockchain and the electrum network for the
needed informations, without sacrificing the cryptographically proof of data.

To do so, at the first run spruned downloads and do POW verification, since the genesis block, of the whole chain of headers,
(and this, paradoxically, makes spruned faster to sync on mainnet than testnet).
Headers are saved into a sqlite database. The first ~130mb (250mb on testnet) are gone.

At this point (it takes 15~30 minutes on a modern server, ~2 hours on a RPI zero), spruned is ready to serve headers,
block and transactions.

Headers are downloaded from the Electrum network.

Usage of the bitcoind p2p network
---------------------------------
At this very moment, spruned usage of the p2p network is limited to the blocks download.

Once the headers are synced to the best one available in the Electrum network, a set of connection to the p2p network
is initialized, target is to keep the default value of 8 connections.

Everytime the ```getblock``` command is used, a local cache layer is queried to check if the block was previously saved.
If the block is found, no network calls are made, otherwise the block is downloaded from a random peer of the network,
taken from the established connections pool.

Remote peers, however, already notify new transactions to spruned, and the mempool emulation is WIP. This will be
the second usage of the P2P network in this first stage.


Usage of the electrum network
-----------------------------
The electrum network is used for multiple purposes. Transactions, fees, headers, a lot of data is fetched from the
electrum servers.


- getrawtransaction
- sendrawtransaction
- getblockheader
- estimatefee



Needs the electrum network to work properly.
Also, to crypto-verify a transaction, the tx merkle proof is downloaded from the electrum network.

Dependencies
------------

For sake of coding speed, right now spruned relay on a set of open source code dependecies. It would be nice in the
future to reduce this set of dependencies.
Right now dependencies are a necessary evil.


When you install spruned, you will also use:

- async-timeout==2.0.1
- jsonrpcserver==3.5.3
- sqlalchemy==1.2.6
- coverage==4.5.1
- plyvel==0.9.0
- daemonize==2.4.7
- aiohttp==3.0.0b0
- git+https://github.com/gdassori/pybitcointools.git@spruned-support#egg=pybitcointools-1.0.0a1
- git+https://github.com/gdassori/connectrum.git@spruned-support#egg=connectrum-0.5.3a4
- git+https://github.com/gdassori/pycoinnet.git@spruned-support#egg=pycoinnet-0.19a3
- git+https://github.com/gdassori/pycoin.git@spruned-support#egg=pycoin-0.90a4


daemonize is self explaining, it helped me to put spruned in background (can be easily removed).

plyvel is the LevelDB driver, no way this will be removed.

aiohttp and coverage are used only for testing, can be installed separately.

async-timeout is a well known library and cannot be replaced unless recoded.

there's no large usage of sqlalchemy, and can be removed, but the whole transactional sqlite part must be recoded.

jsonrpc is a well known and trusted dependency, I don't feel the need to remove it.

A different chapter must be open for the github dependencies.

I personally mantain this pybitcointools fork, and I don't feel the need to remove it.

Connectrum can be removed, but must be recoded, and however Coinkite (the mantainer) is very well reputed in the crypto ecosystem.

pycoin and pycoinnet from Richard Kiss are very large reviewed and respectful libraries of the crypto ecosystem.

No need to remove them but... I do a very small usage of the pycoin library (and a huge usage of pycoinnet!) so I may,
in the future, think about removing only the pycoin dependency.

Todo
----

A lot must be done, and spruned is just in its early stage. My first goal would be to find fellow developers that contribute
to the project :-)

With them I would love to do the mempool emulation, reduce the dependency from the electrum network,
write an extensive integration tests suite and many other things. This library can be promising, but without extensive
review from different people, me neither would advice its usage in a production environment.
