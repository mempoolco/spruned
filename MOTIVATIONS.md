## sPRUNED Motivations



#### Long short story


Let's say you (I, when I started writing this) have a small VPS server, and you (yeah, I, again) want to test some fancy bitcoin stuff that
requires not-pruned nodes (or you (yeah, this is YOU) want to [setup a chaindns domain](https://github.com/chaindns/chaindnsd)). 

Well, "setup your own full node and contribute to decentralization! It take just some $ at year!"

Cool, but it takes resources, and you don't have them a.t.m.. 
C'mon, you simply need another option! Everyone should have another option!

So, WHILE you set up your full node (and **obviously** then partecipate to sPRUNED network as a SP 
[stands for sPRUNED Provider]), you can extend your BitcoinRPC API with sPRUNED.


#### sPRUNED is (not) cool

It uses centralized services to leech informations you can instead gather in a decentralized autonomous network.

**But**, for your protection, uses your local pruned node and local consensus verification on services responses to ensure 
fetched data match reality. 
So you leech data around the internet (contribute and increase sources), but you antonomous verify it with your pruned local node.

**Aaaand**, if you are _very_ hurry and want to pre-fetch a local node, you can download an updated snapshot [here](#).


#### Ok, maybe is not bad at all.

It's true. You don't help Blockchain decentralization, using sPRUNED.
But you can definitely trust what you see.


#### sPRUNED is slow. 

It uses remote resources instead of local data. Also, it uses blocking synchronous calls a.t.m. 
(will change, but once sync version algos are well established). 


#### sPRUNED it not _so_ slow.

- You can bootstrap sPRUNED to enable blockheaders API on fly.
- You can enable local cache.
- You can use A.I. and speculative execution to pre-fetch data around your requests. [no ok, I'm, kidding]

**Bootstrapping** in sPRUNED download the whole block headers, so you can have getblockheader on pruned node.

**Cache** is file-based or redis-based, if enabled avoid to gather data two times (if cacheable).
