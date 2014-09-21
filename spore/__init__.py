'''

Spore
=====

Spore is a simple p2p networking library.

Getting started
---------------

Here's an example to get you started::

    from spore import Spore

    spore_example = Spore(seeds=[('spore-example.eudemonia.io', 39406)], address=('0.0.0.0', 39406))

    @spore_example.on_connect
    def say_hello(peer, message):
        peer.send('greeting', b'Hello, friend!')

    @spore_example.handler('greeting')
    def greeting(peer, message):
        if len(message) < 50:
            print(str(peer.address) + " said: " + message + " to us!")

'''

import asyncio
import threading
import sys
import socket
import collections
import random
from .structs import Message, Peer, Info

DEBUG = False

def print_line(*args):
    if DEBUG:
        print(*args)

class Spore(object):
    class Protocol(asyncio.Protocol):
        def __init__(self, spore):
            self._spore = spore
            self._buffer = bytearray()
            self._transport = None

            self.nonce = None
            self.data = dict()

            print_line("Spore.Protocol: created..")

        def __str__(self):
            return "Spore Protocol Object: connected to " + str(self.address)

        def connection_made(self, transport):
            print_line("Spore.Protocol: connection made..")
            # TODO: check if we're full, and let them know.
            self.address = transport.get_extra_info('peername')

            print_line("Spore.Protocol: got addr..")

            if not self._spore._should_connect_to(self.address):
                print_line("Spore.Protocol will not connect to", self.address)
                transport.close()
                return

            # _transport must be set when we add this to spore's list.
            # See the connection_lost method.
            self._spore._protocols.append(self)
            self._transport = transport

            print_line("Spore.Protocol Sending info..")

            port = self._spore._address[1] if self._spore._address else None
            info = Info(version=0, nonce=self._spore._nonce, port=port)
            self.send('spore_info', info)


        def send(self, method, payload=b''):
            if hasattr(payload, 'to_json'):
                payload = payload.to_json().encode()
            message = Message(method=method, payload=payload).to_json()
            print_line("Spore.Protocol: writing transport")
            self._transport.write((message + "\n").encode())

        def data_received(self, data):
            # TODO: refactor this out so we can support more than just JSON
            print_line("Spore.Protocol.data_received:", data)
            for byte in data:
                self._buffer.append(byte)
                if self._buffer[-1] == 10:
                    try:
                        s = self._buffer.decode()
                    except UnicodeDecodeError:
                        # Invalid message was sent, drop the connection.
                        self._transport.close()
                        return
                    message = Message.from_json(s)
                    for callback, deserialize in self._spore._on_message_callbacks[message.method]:
                        if deserialize:
                            callback(self, deserialize(message.payload.decode()))
                        else:
                            callback(self, message.payload)
                    self._buffer.clear()

        def connection_lost(self, exc):
            # If _transport is set, then we added it to spore's list.
            # Otherwise we did not add it to spore's list, instead
            # we closed immediately, so no action is necessary here.
            if self._transport:
                for callback in self._spore._on_disconnect_callbacks:
                    callback(self)
                if self.nonce in self._spore._map_nonce_to_client:
                    self._spore._map_nonce_to_client.pop(self.nonce)
                self._spore._protocols.remove(self)
                if len(self._spore._protocols) == 0:
                    asyncio.Task(self._spore._notify_protocols_empty(), loop=self._spore._loop)

    def __init__(self, seeds=[], address=None, source_ip=None, debug=False):
        self._loop = None
        self._main_thread = None
        self._protocols = []
        self._clients = []
        self._server = None
        self._known_addresses = seeds
        self._try_new_connections = None
        self._source_ip = source_ip
        self._address = address
        self._main_task = None
        self._on_connect_callbacks = []
        self._on_disconnect_callbacks = []
        self._on_message_callbacks = collections.defaultdict(list)
        self._nonce = random.randint(0, 2 ** 32 - 1)  # nonce should be unique for any and all peers
        self._map_nonce_to_client = {self._nonce: None}
        self._map_address_to_last_nonce = {address: self._nonce}
        self._debug = debug

        @self.on_message('peer', Peer.from_json)
        def receive_peer(from_peer, new_peer):
            # TODO: track which peers know about which peers to reduce traffic by a factor of two.
            # TODO: Do not relay this peer if it's on a network that is unreachable.
            address = (socket.inet_ntoa(new_peer.ip), new_peer.port)
            if address not in self._known_addresses:
                self.broadcast('peer', new_peer, exclude=from_peer)
                self._known_addresses.append(address)
                self._try_new_connections.set()


        @self.on_message('spore_info', Info.from_json)
        def info(peer, info):
            print_line("Spore: spore_info received.")
            if info.nonce in self._map_nonce_to_client:
                peer._transport.close()
                print_line("Spore: closing transport")
            else:
                self._map_nonce_to_client[info.nonce] = peer
                peer.nonce = info.nonce
                if info.port:
                    receive_peer(peer, Peer(ip=socket.inet_aton(peer.address[0]), port=info.port))
                for address in self._known_addresses:
                    peer.send('peer', Peer(ip=socket.inet_aton(address[0]), port=address[1]))
                for callback in self._on_connect_callbacks:
                    callback(peer)


    def on_connect(self, func):
        self._on_connect_callbacks.append(func)
        return func

    def on_disconnect(self, func):
        self._on_disconnect_callbacks.append(func)
        return func

    def on_message(self, method, deserialize=None):
        def wrapper(func):
            self._on_message_callbacks[method].append((func, deserialize))
            return func

        return wrapper

    def handler(self, method):
        return self.on_message(method)

    def broadcast(self, method, data, exclude=[]):
        if hasattr(data, 'serialize'):
            data = data.serialize()
        for protocol in self._protocols:
            if not isinstance(exclude, list):
                exclude = [exclude]
            if protocol not in exclude:
                protocol.send(method, data)

    def num_connected_peers(self):
        return len(self._protocols)

    def run(self):

        # First, set the event loop.
        self._loop = asyncio.new_event_loop()
        self._try_new_connections = asyncio.Event(loop=self._loop)
        self._try_new_connections.set()
        self._protocols_empty_cv = asyncio.Condition(loop=self._loop)
        self._main_thread = threading.current_thread()

        # Sanity check.
        assert self._main_task is None

        # Set up main task.
        coroutines = [self._create_server(), self._connect_loop()]
        self._main_task = asyncio.Task(asyncio.wait(coroutines, loop=self._loop), loop=self._loop)

        # Run them
        try:
            self._loop.run_until_complete(self._main_task)
        except (asyncio.CancelledError, KeyboardInterrupt):
            complete = self._loop.run_until_complete(self._clean_up())

        self._main_task = None
        self._loop.close()
        self._loop = None

    def shutdown(self):
        if self._main_task is None:
            sys.stderr.write("Warning: shutdown called on spore instance that is stopped.\n")
        else:
            self._loop.call_soon_threadsafe(self._main_task.cancel)
            self._main_thread.join()
            self._main_thread = None

    def _protocol_factory(self):
        return Spore.Protocol(self)

    def _should_connect_to(self, address):
        ip, port = address
        # TODO: implement banning.
        if address in self._map_address_to_last_nonce:
            if self._map_address_to_last_nonce[address] in self._map_nonce_to_client:
                return False
        for protocol in self._protocols:
            # connect to localhost in debug
            if protocol.address[0] == ip and not self._debug:
                return False
                # TODO: check other ways in which this peer might prevent us from connecting to address
        return True

    @asyncio.coroutine
    def _clean_up(self):
        for protocol in self._protocols:
            protocol._transport.close()
        if self._server:
            self._server.close()
        yield from self._wait_protocols_empty()

    @asyncio.coroutine
    def _connect_loop(self):
        while True:
            yield from self._try_new_connections.wait()
            self._try_new_connections.clear()

            try_again = False

            # Try connecting to all peers.
            for ip, port in self._known_addresses:
                if self._should_connect_to((ip, port)):
                    try:
                        #print_line("Spore: doing something..")
                        local_addr = None
                        if self._source_ip:
                            local_addr = (self._source_ip, 0)
                        result = yield from self._loop.create_connection(self._protocol_factory, ip, port,
                                                                         local_addr=local_addr)
                        print_line(result)
                        print_line((ip, port))
                    except (ConnectionRefusedError, ConnectionResetError):
                        # If there's something to try that failed, try again real quick.
                        # This is mostly useful for tests.
                        try_again = True
                        # TODO: mark that this peer should not be tried for a while
                        #       (perhaps there is a better way to do this logic anyway, on a per-known-address basis?)
                        # TODO: increase misbehaving for that peer.

            self._loop.call_later(0.05 if try_again else 5, self._try_new_connections.set)

    @asyncio.coroutine
    def _create_server(self):
        if self._address:
            print_line("Spore: attempting to create server..")
            self._server = yield from self._loop.create_server(self._protocol_factory, *self._address)
            print_line(self._server.sockets)

    @asyncio.coroutine
    def _wait_protocols_empty(self):
        if len(self._protocols) != 0:
            with (yield from self._protocols_empty_cv):
                yield from  self._protocols_empty_cv.wait()

    @asyncio.coroutine
    def _notify_protocols_empty(self):
        with (yield from self._protocols_empty_cv):
            self._protocols_empty_cv.notify_all()
