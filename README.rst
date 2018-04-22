sPRUNED
-------

A Bitcoin lightweight pseudonode with RPC that can fetch any block or transaction
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

|travis| |coveralls| |pypi| 

What's this?
^^^^^^^^^^^^^

sPRUNED is a bitcoin client for light systems. 256mb ram & 500mb hdd
should be fairly enough to keep it up & running.

Supports both Bitcoin Mainnet and Testnet It's a replacement for
bitcoind on lightweight systems (It's proven to work on a Raspberry
Zero, along with CLightning), it provides an interface for bitcoin-cli.

How it works?
^^^^^^^^^^^^^

spruned downloads and store the bitcoin blocks on demand, when you need
them, directly from the Peer2Peer Bitcoin Network. there's a "bootstrap"
functionality, to keep the last ~50 (default settings) blocks on the
local storage, because fetch blocks may require also up to 10 seconds
with slow connections, and this "bootstrap mode" reduces latencies on
usage.

You can use bitcoin-cli, or any other RPC client, as if you had bitcoind
up & running. For the transactions related APIs and utxo tracking,
spruned uses the electrum network.

Documentation
^^^^^^^^^^^^^

-  `Installation and usage on Raspberry Pi (Raspbian
   9.3) <docs/rpi-b-2012.md>`__

Dependencies
^^^^^^^^^^^^

spruned works with Python >= 3.5.2. Right now it should work only on
Linux systems. It make intensive usage of connectrum, pybitcointools and
pycoinnet libraries. Thanks to mantainers & contributors! Especially at
this stage of development (but it would be better always), it is
recommended to use virtualenv to run spruned.

Usage
^^^^^

Developers: I hope code is self explaining enough, if you're familiar
with asyncio.

Everyone else: You can get inspiration on how to install spruned taking
a look at setup.sh but, if you're lucky enough, setup.sh itself will
create a virtual environment and install spruned into it.

Well, try this:

::

    $ cd ~/src
    $ sudo apt-get install libleveldb-dev python3-dev git virtualenv
    $ git clone https://github.com/gdassori/spruned.git
    $ cd spruned
    $ ./setup.sh
    $ venv/bin/python spruned.py --help
    usage: spruned.py [-h] [--rpcuser RPCUSER] [--rpcpassword RPCPASSWORD]
                      [--rpcport RPCPORT] [--rpcbind RPCBIND] [--datadir DATADIR]
                      [--daemon] [--keep-blocks KEEP_BLOCKS]
                      [--network {bitcoin.mainnet,bitcoin.testnet}] [--debug]
                      [--cache-size CACHE_SIZE]

    A Bitcoin Lightweight Pseudonode

    optional arguments:
      -h, --help            show this help message and exit
      --rpcuser RPCUSER     Username for JSON-RPC connections (default: rpcuser)
      --rpcpassword RPCPASSWORD
                            Password for JSON-RPC connections (default:
                            rpcpassword)
      --rpcport RPCPORT     Listen for JSON-RPC connections on <port> (default:
                            8332 or testnet: 18332) (default: 8332)
      --rpcbind RPCBIND     Bind to given address to listen for JSON-RPC
                            connections. (default: 127.0.0.1)
      --datadir DATADIR     Specify data directory (default: /home/guido/.spruned)
      --daemon              Run in the background as a daemon and accept commands
                            (default: False)
      --keep-blocks KEEP_BLOCKS
      --network {bitcoin.mainnet,bitcoin.testnet}
      --debug               Enable debug mode (default: False)
      --cache-size CACHE_SIZE
                            Cache size (in megabytes) (default: 50)

And, once you run spruned:

::

    $ tail -f ~/.spruned/spruned.log # to see what's going on!

or check the status\*:

::

    $ bitcoin-cli getblockchaininfo
    {
      "mediantime": 1523387051,
      "blocks": 517579,
      "headers": 517579,
      "verificationprogress": 100,
      "chain": "main",
      "chainwork": null,
      "difficulty": null,
      "bestblockhash": "00000000000000000018e502dec1f93d32521674019a45d7d095cbd390279dff",
      "warning": "spruned v0.0.1. emulating bitcoind v0.16",
      "pruned": false
    }

Download a block:

::

    $ bitcoin-cli getblock `bitcoin-cli getblockhash 1`
    {
      "bits": 486604799,
      "mediantime": 1231469665,
      "nextblockhash": "000000006a625f06636b8bb6ac7b960a8d03705d1ace08b1a19da3fdcc99ddbd",
      "tx": [
        "0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098"
      ],
      "previousblockhash": "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
      "version": 1,
      "chainwork": "Not Implemented Yet",
      "nonce": 2573394689,
      "time": 1231469665,
      "height": 1,
      "hash": "00000000839a8e6886ab5951d76f411475428afc90947ee320161bbf18eb6048",
      "versionHex": "Not Implemented Yet",
      "merkleroot": "0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098",
      "difficulty": "Not Implemented Yet"
    }

Or a transaction:

::

    $ bitcoin-cli getrawtransaction 0e3e2357e806b6cdb1f70b54c3a3a17b6714ee1f0e68bebb44a74b1efd512098
    01000000010000000000000000000000000000000000000000000000000000000000000000ffffffff0704ffff
    001d0104ffffffff0100f2052a0100000043410496b538e853519c726a2c91e61ec11600ae1390813a627c66fb
    8be7947be63c52da7589379515d4e0a604f8141781e62294721166bf621e73a82cbf2342c858eeac00000000

And, eventually, broadcast a transaction:

::

    $ bitcoin-cli sendrawtransaction 01000000011cee4c0dd7f1a90ae80311c414d48f3a16596e9ea08fa3edfb793734e2b2a100010000006a47304402205a665616085b4f425cccfde5be2113258f3c104c2c53ef918866ada8f02f7caf0220458bdbc220a3f1017b65d9138e5121a9c63decc89550a2e64e914013d26cb93b0121029643906e277eae677134d40356dfb575a2dfbe09a18a1fd7fadfd853715a7242ffffffff0234e3e600000000001976a91410a71790c6bbc2694c74b6fee9a449a11f74123388ac444c5501000000001976a9148c9e0a9029bbce075e2b5aae90010905aa4c64b188ac00000000
    489feae0e317b9255031710eadc238bb1ba3009fff0e86b303b0963e34a332b0

*\* bitcoin-cli is not included*

Emulated APIs as in bitcoind 0.16:
''''''''''''''''''''''''''''''''''

::

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
    - sendrawtransaction

Work in progress:
'''''''''''''''''

::

    - getrawtransaction [ verbose ]
    - getmempoolinfo
    - getrawmempool

Requirements
^^^^^^^^^^^^

-  An internet connection
-  **less than 500mb of disk space :-)**
-  Python >= 3.5.2

Limitations
^^^^^^^^^^^

-  May reduce privacy: if you have the entire blockchain on your own,
   you have to tell no one what you're looking for.
-  Not fast as a full node: internet download is slower than a read from
   disk.
-  Doesn't relay and partecipate to the network (this may change).
-  Very unstable!

Future development
^^^^^^^^^^^^^^^^^^

-  Full Tor support
-  Mempool emulation
-  Zeromq emulation
-  Maintenance UI

.. |travis| image:: https://travis-ci.org/gdassori/spruned.svg?branch=master
   :target: https://travis-ci.org/gdassori/spruned
.. |coveralls| image:: https://coveralls.io/repos/github/gdassori/spruned/badge.svg
   :target: https://coveralls.io/github/gdassori/spruned
.. |pypi| image:: https://badge.fury.io/py/spruned.svg
   :target: https://pypi.org/project/spruned/
