Getting Started with spruned
============================

Installation
------------

To install spruned, run this command in the terminal::

    $ cd ~/src
    $ sudo apt-get install libleveldb-dev python3-dev git virtualenv
    $ git clone https://github.com/gdassori/spruned.git
    $ cd spruned
    $ virtualenv -p python3.5 venv
    $ . venv/bin/activate
    $ pip install -r requirements.txt
    $ python setup.py install


Then you will have a $USER/src/spruned folder with a dedicated python interpreter.
The usage of a virtual environment is warmly advised.

Usage
-----

As with bitcoind, also with spruned you can hit the '--help' argument, to see how to configure it::

   $ ~/src/spruned/venv/bin/spruned --help



And, as in bitcoind, you can set up a config file with the parameters listed::

   $ nano ~/.spruned/spruned.conf



And you can put into it, for instance, the RPC settings::

   rpcuser=your_username
   rpcpassword=your_password
   rpcport=18332
   rpcbind=0.0.0.0
   network=bitcoin.testnet


