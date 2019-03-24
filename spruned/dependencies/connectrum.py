# Connectrum
# Original: https://github.com/coinkite/connectrum
# Fork & Personal release:  https://github.com/gdassori/connectrum
#

# Connectrum
# ----------
#
# Stratum (electrum-server) Client Protocol library
# =================================================
#
# Uses python3 to be a client to the Electrum server network. It makes heavy use of
# `asyncio` module and newer Python 3.5 keywords such as `await` and `async`.
#
# For non-server applications, you can probably find all you need
# already in the standard Electrum code and command line.
#
# Python 3.5 is absolutely required for this code. It will never work
# on earlier versions of Python.
#
#
# Features
# ========
#
# - can connect via Tor, SSL, proxied or directly
# - filter lists of peers by protocol, `.onion` name
# - manage lists of Electrum servers in simple JSON files.
# - fully asynchronous design, so can connect to multiple at once
# - a number of nearly-useful examples provided
#
# Examples
# ========
#
# In `examples` you will find a number little example programs.
#
# - `cli.py` send single commands, plan is to make this an interactive REPL
# - `subscribe.py` stream changes/events for an address or blocks.
# - `explorer.py` implements a simplistic block explorer website
# - `spider.py` find all Electrum servers recursively, read/write results to JSON
#
# Version History
# ===============
#
# - **0.5.3** Documents the build/release process (no functional changes).
# - **0.5.2** Make aiosocks and bottom modules optional at runtime (thanks to @BioMike)
# - **0.5.1** Minor bug fixes
# - **0.5.0** First public release.
#
#
# TODO List
# =========
#
# - be more robust about failed servers, reconnect and handle it.
# - connect to a few (3?) servers and compare top block and response times; pick best
# - some sort of persistant server list that can be updated as we run
# - type checking of parameters sent to server (maybe)?
# - lots of test code
# - an example that finds servers that do SSL with self-signed certificate
# - an example that fingerprints servers to learn what codebase they use
# - some bitcoin-specific code that all clients would need; like block header to hash


#  LICENSE
#  The MIT License (MIT)
#
#  Copyright (c) 2016 by Coinkite Inc.
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy of
#  this software and associated documentation files (the "Software"), to deal in
#  the Software without restriction, including without limitation the rights to
#  use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
#  the Software, and to permit persons to whom the Software is furnished to do so,
#  subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in all
#  copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
#  FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
#  COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
#  IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
#  CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
#

#
# Client connect to an Electrum server.
#

# Runtime check for optional modules
from importlib import util as importutil
from collections import defaultdict
import asyncio
import ssl
import logging
import time
import json

# Check if aiosocks is present, and load it if it is.

if importutil.find_spec("aiohttp_socks") is not None:
    import aiohttp_socks
    have_aiosocks = True
else:
    have_aiosocks = False

logger = logging.getLogger(__name__)


class ElectrumErrorResponse(RuntimeError):
    pass


class StratumProtocol(asyncio.Protocol):
    client = None
    closed = False
    transport = None
    buf = b""

    def connection_made(self, transport):
        self.transport = transport
        logger.debug("Transport connected ok")

    def connection_lost(self, exc):
        if not self.closed:
            self.closed = True
            self.close()
            self.client and self.client.connection_lost(self)

    def data_received(self, data):
        self.buf += data
        *lines, self.buf = self.buf.split(b'\n')
        for line in lines:
            if not line:
                continue
            try:
                msg = line.decode('utf-8', "error").strip()
            except UnicodeError:
                logger.exception("Encoding issue on %r" % line)
                continue
            try:
                msg = json.loads(msg)
            except ValueError:
                logger.exception("Bad JSON received from server", msg)
                continue
            try:
                self.client.got_response(msg)
            except Exception as e:
                logger.exception("Trouble handling response! (%s)" % e)
                continue

    def send_data(self, message):
        """
        Given an object, encode as JSON and transmit to the server.
        """
        data = json.dumps(message).encode('utf-8') + b'\n'
        self.transport.write(data)

    def close(self):
        if not self.closed:
            try:
                self.transport.close()
            finally:
                self.closed = True


class StratumClient:
    def __init__(self, loop=None):
        """
        Setup state needed to handle req/resp from a single Stratum server.
        Requires a transport (TransportABC) object to do the communication.
        """
        self.protocol = None
        self.disconnect_callback = None
        self.server_info = None
        self.proto_code = None
        self.next_id = 1
        self.inflight = {}
        self.subscriptions = defaultdict(list)
        self.ka_task = None
        self.keepalive_interval = 300
        self.loop = loop or asyncio.get_event_loop()
        self.server_version = None

    def connection_lost(self, protocol):
        self.disconnect_callback and self.disconnect_callback(self)
        if protocol is not self.protocol:
            return
        self.protocol = None
        logger.warning("Electrum server connection lost")
        if self.ka_task:
            self.ka_task.cancel()
            self.ka_task = None

    def close(self):
        if self.protocol:
            self.protocol.close()
            self.protocol = None
        if self.ka_task:
            self.ka_task.cancel()
            self.ka_task = None

    async def connect(self, server_info, proto_code=None, *,
                      disable_cert_verify=False,
                      proxy=None, short_term=False, disconnect_callback=None,
                      ignore_version=True):
        """
        Start connection process.
        Destination must be specified in a ServerInfo() record (first arg).
        """
        self.disconnect_callback = disconnect_callback
        self.server_info = server_info
        if not proto_code:
            proto_code, *_ = server_info.protocols
        self.proto_code = proto_code

        logger.debug("Connecting to: %r" % server_info)
        hostname, port, use_ssl = server_info.get_port(proto_code)

        if use_ssl and disable_cert_verify:
            # Create a more liberal SSL context that won't
            # object to self-signed certicates. This is
            # very bad on public Internet, but probably ok
            # over Tor
            use_ssl = ssl.create_default_context()
            use_ssl.check_hostname = False
            use_ssl.verify_mode = ssl.CERT_NONE

        if proxy:
            if have_aiosocks:
                transport, protocol = await aiohttp_socks.create_connection(
                    protocol_factory=StratumProtocol, socks_url=proxy,
                    rdns=True, ssl=use_ssl,
                    host=hostname, port=port, server_hostname=hostname)
            else:
                logger.debug("Error: want to use proxy, but no aiosocks module.")
        else:
            transport, protocol = await self.loop.create_connection(
                StratumProtocol, host=hostname,
                port=port, ssl=use_ssl)
        if self.protocol:
            self.protocol.close()

        self.protocol = protocol
        protocol.client = self

        try:
            payload = '%s %s' % (self.server_info['nickname'], self.server_info['local_version'])
            self.server_version = await self.RPC('server.version', payload, self.server_info['local_version'])
            if not ignore_version:
                res = await self.RPC('blockchain.scripthash.listunspent', '0' * 64)
                if isinstance(res, Exception):
                    raise res
        except Exception:
            logger.debug('Unsupported protocol version: %s', self.server_info['local_version'])
            try:
                self.protocol.close()
            except:
                pass
            self.protocol = None
            raise

        if not short_term:
            self.ka_task = self.loop.create_task(self._keepalive())

        logger.debug("Connected to: %r" % server_info)

    async def _keepalive(self):
        """
        Keep our connect to server alive forever, with some
        pointless traffic.
        """
        while self.protocol:
            payload = '%s %s' % (self.server_info['nickname'], self.server_info['local_version'])
            vers = await self.RPC('server.version', payload, self.server_info['local_version'])
            logger.debug("Server version: %s", vers)
            await asyncio.sleep(self.keepalive_interval)

    def _send_request(self, method, params=list(), is_subscribe=False):
        """
        Send a new request to the server. Serialized the JSON and
        tracks id numbers and optional callbacks.
        """
        # pick a new ID
        self.next_id += 1
        req_id = self.next_id

        # serialize as JSON
        msg = {'id': req_id, 'method': method, 'params': params}

        # subscriptions are a Q, normal requests are a future
        waitQ = None

        if is_subscribe:
            waitQ = asyncio.Queue()
            self.subscriptions[method].append(waitQ)
        fut = asyncio.Future(loop=self.loop)
        self.inflight[req_id] = (msg, fut)

        # send it via the transport, which serializes it
        self.protocol.send_data(msg)
        return fut if not is_subscribe else (fut, waitQ)

    def got_response(self, msg):
        """
        Decode and dispatch responses from the server.
        Has already been unframed and deserialized into an object.
        """
        resp_id = msg.get('id', None)

        if resp_id is None:
            # subscription traffic comes with method set, but no req id.
            method = msg.get('method', None)
            if not method:
                logger.error("Incoming server message had no ID nor method in it", msg)
                return

            # not obvious, but result is on params, not result, for subscriptions
            result = msg.get('params', None)

            logger.debug("Traffic on subscription: %s" % method)

            subs = self.subscriptions.get(method)
            if not subs:
                return
            for q in subs:
                self.loop.create_task(q.put(result))

            return

        assert 'method' not in msg
        result = msg.get('result')

        # fetch and forget about the request
        inf = self.inflight.pop(resp_id)
        if not inf:
            logger.error("Incoming server message had unknown ID in it: %s" % resp_id)
            return

        # it's a future which is done now
        req, rv = inf
        if 'error' in msg:
            err = msg['error']

            logger.debug("Error response: '%s'" % err)
            rv.set_exception(ElectrumErrorResponse(err, req, self))

        else:
            rv.set_result(result)

    def RPC(self, method, *params):
        assert '.' in method
        return self._send_request(method, list(params))

    def subscribe(self, method, *params):
        assert '.' in method
        assert method.endswith('subscribe')
        return self._send_request(method, list(params), is_subscribe=True)

#
# Store information about servers. Filter and select based on their protocol support, etc.
#


DEFAULT_PORTS = {'t': 50001, 's': 50002, 'h': 8081, 'g': 8082}


class ServerInfo(dict):
    """
    Information to be stored on a server. Based on IRC data that is published.
    Based on a dictionary, which I regret now...
    """
    FIELDS = ['nickname', 'hostname', 'ports', 'version', 'pruning_limit', 'seen_at']

    def __init__(self, nickname_or_dict, hostname=None, ports=None,
                 version=None, pruning_limit=None, ip_addr=None):

        if not hostname and not ports:
            # promote a dict, or similar
            super(ServerInfo, self).__init__(nickname_or_dict)
            return

        self['nickname'] = nickname_or_dict or None
        self['hostname'] = hostname
        self['ip_addr'] = ip_addr or None
        self['local_version'] = version

        # For 'ports', take
        # - a number (int), assumed to be TCP port, OR
        # - a list of codes, OR
        # - a string to be split apart.
        # Keep version and pruning limit separate
        #
        if isinstance(ports, int):
            ports = ['t%d' % ports]
        elif isinstance(ports, str):
            ports = ports.split()

        # check we don't have junk in the ports list
        for p in ports.copy():
            if p[0] == 'v':
                version = p[1:]
                ports.remove(p)
            elif p[0] == 'p':
                try:
                    pruning_limit = int(p[1:])
                except ValueError:
                    # ignore junk
                    pass
                ports.remove(p)

        assert ports, "Must have at least one port/protocol"

        self['ports'] = ports
        self['version'] = version
        self['pruning_limit'] = int(pruning_limit or 0)

        self['seen_at'] = time.time()

    @classmethod
    def from_dict(cls, d):
        n = d.pop('nickname')
        h = d.pop('hostname')
        p = d.pop('ports')
        rv = cls(n, h, p)
        rv.update(d)
        return rv

    @property
    def protocols(self):
        rv = set(self['ports'])
        assert 'p' not in rv, 'pruning limit got in there'
        assert 'v' not in rv, 'version got in there'
        return rv

    @property
    def pruning_limit(self):
        return self.get('pruning_limit', 100)

    @property
    def hostname(self):
        return self.get('hostname')

    def get_port(self, for_protocol):
        """
        Return (hostname, port number, ssl) pair for the protocol.
        Assuming only one port per host.
        """
        assert len(for_protocol) == 1, "expect single letter code"
        rv = [i[0] for i in self['ports'] if i[0] == for_protocol]
        port = None
        if len(rv) >= 2:
            try:
                port = int(rv[1:])
            except:
                pass
        port = port or DEFAULT_PORTS[for_protocol]
        use_ssl = for_protocol in ('s', 'g')
        return self['hostname'], port, use_ssl

    @property
    def is_onion(self):
        return self['hostname'].lower().endswith('.onion')

    def __repr__(self):
        return '<ServerInfo {hostname} nick={nickname} ports="{ports}" v={version} prune={pruning_limit}>'\
                                        .format(**self)

    def __str__(self):
        return self['hostname'].lower()
