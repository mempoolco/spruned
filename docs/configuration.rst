Configuration
=============

Is easy to configure spruned! Some parameters are the same of bitcoind. Something else is part of spruned only. Let's see.


RPC
---

spruned try to emulate the bitcoind RPC interface, so can work with bitcoin-cli. To do so, if you use config files,
the must be aligned.


Those two files:

::
  ~/.bitcoin/bitcoin.conf
  ~/.spruned/spruned.conf



Must have the same configuration for the following parameters:

::
  rpcuser
  rpcpassword
  rpcbind
  rpcport



And bitcoin-cli will be able to communicate with spruned as it would do with bitcoind.

Cache
-----


Other
-----

debug
-----


