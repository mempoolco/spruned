Commands
========

Supported bitcoind API in spruned


Blockchain
----------
- getbestblockhash
- getblock "blockhash" ( verbosity )
- getblockchaininfo
- getblockcount
- getblockhash height
- getblockheader "hash" ( verbose )
- gettxout "txid" n ( include_mempool )

Rawtransactions
---------------
- getrawtransaction "txid" ( verbose )
- sendrawtransaction "hexstring" ( allowhighfees )

Util
----
- estimatefee nblocks
- estimatesmartfee conf_target ("estimate_mode")
