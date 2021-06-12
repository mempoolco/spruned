import asyncio
import tempfile


@asyncio.coroutine
def create_pipe_pairs(protocol_factory):
    path = tempfile.mktemp()
    loop = asyncio.get_event_loop()
    server_side = asyncio.Future()

    def server_callback():
        p = protocol_factory()
        server_side.set_result(p)
        return p

    server = yield from loop.create_unix_server(server_callback, path)
    t1, p1 = yield from loop.create_unix_connection(protocol_factory, path)
    p2 = yield from server_side
    server.close()
    return p1, p2


@asyncio.coroutine
def create_pipe_streams_pair():
    path = tempfile.mktemp()
    loop = asyncio.get_event_loop()
    server_side = asyncio.Future()

    def factory():

        def client_connected_cb(reader, writer):
            server_side.set_result((reader, writer))
        reader = asyncio.StreamReader(loop=loop)
        return asyncio.StreamReaderProtocol(reader, client_connected_cb, loop=loop)

    server = yield from loop.create_unix_server(factory, path)

    r1 = asyncio.StreamReader(loop=loop)
    protocol = asyncio.StreamReaderProtocol(r1, loop=loop)
    transport, _ = yield from loop.create_unix_connection(
        lambda: protocol, path)
    w1 = asyncio.StreamWriter(transport, protocol, r1, loop)

    r2, w2 = yield from server_side
    server.close()
    return (r1, w1), (r2, w2)


class DirectTransport(asyncio.Transport):

    DEFAULT_LATENCY = 2.0

    def __init__(self, remote_protocol, latency=None, loop=None):
        self._remote_protocol = remote_protocol
        self._loop = loop or asyncio.get_event_loop()
        self._latency = latency if latency is not None else self.DEFAULT_LATENCY
        self._is_closing = False
        self._extra = {}

    def write(self, data):
        if self._is_closing:
            return
        self._loop.call_later(self._latency, self._remote_protocol.data_received, data)

    def close(self):
        def later():
            try:
                self._remote_protocol.eof_received()
            except Exception:
                pass
            self._remote_protocol.connection_lost(None)
        self._loop.call_later(self._latency, later)
        self._is_closing = True

    def is_closing(self):
        return self._is_closing


def create_direct_transport_pair(protocol_factor_1, protocol_factor_2=None, latency=None, loop=None):
    protocol_factor_2 = protocol_factor_2 or protocol_factor_1
    p1 = protocol_factor_1()
    p2 = protocol_factor_2()
    t1 = DirectTransport(p2, latency=latency, loop=loop)
    t2 = DirectTransport(p1, latency=latency, loop=loop)
    p1.connection_made(t1)
    p2.connection_made(t2)
    return (t1, p1), (t2, p2)


def create_direct_streams_pair(loop=None, latency=None):
    loop = loop or asyncio.get_event_loop()
    r1 = asyncio.StreamReader(loop=loop)
    r2 = asyncio.StreamReader(loop=loop)

    def protocol_f(reader):
        def f():
            return asyncio.StreamReaderProtocol(reader, loop=loop)
        return f
    (t1, p1), (t2, p2) = create_direct_transport_pair(protocol_f(r1), protocol_f(r2))
    w1 = asyncio.StreamWriter(t1, p1, r1, loop)
    w2 = asyncio.StreamWriter(t2, p2, r2, loop)
    return (r1, w1), (r2, w2)
