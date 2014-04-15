import json
from .spore_pb2 import Peer as PeerFixme, Peerlist, Info, Message
import random
import traceback
import collections
import random
import signal
import sys
import socket
import threading
import time

MAX_OUTBOUND_CONNECTIONS = 50
MAX_INBOUND_CONNECTIONS = 50

class Address(object):
	def __init__(self, address):
		self.host = socket.inet_ntoa(address[0])
		self.port = int.from_bytes(address[1],'big')
		self.t = (self.host, self.port)
	def __getitem__(self, key):
		return self.t[key]

"""
class SporeMessage(Field):
  def fields():
    method = String(max_length=100)
    payload = Bytes()
"""

class Peer(object):

  def __init__(self, spore, address, misbehavior=0):

    # Reference to this peer's main recv_loop thread
    self.recv_loop_thread = None

    # Lock for when sending on this peer's socket.
    self.send_lock = threading.Lock()

    # Lock for when recv'ing on this peer's socket.
    self.recv_lock = threading.Lock()

    # Lock for when either connecting or disconnecting.
    self.socket_lock = threading.Lock()

    # Reference to the spore instance (e.g. for connection limit semaphores)
    self.spore = spore

    # The socket that this peer is communicating over.
    self.socket = None

    # The address of this peer as a tuple (host, port)
    self.address = address

    # This misbehavior of this peer.
    # FIXME: This should be per host.
    self.misbehavior = misbehavior
    
    # A dictionary which can be written to for general use.
    self.data = {}

  def send(self, method, payload=b''):
    # TODO: handle socket error
    with self.send_lock:
      # TODO: fix concurrency issues here with self.socket_lock
      if self.socket:
        try:
          # TODO:fix serialization...
          data = Message(method=method,payload=payload).SerializeToString()
          length = len(data)
          self.socket.sendall(length.to_bytes(4,'big'))
          self.socket.sendall(data)
        except (BrokenPipeError, OSError):
          self.disconnect()

  def is_connected(self):
    """ Returns if this peer is connected. Only valid at the time of the call,
        as the socket may close at any time.
    """
    return self.socket is not None

  def is_banned(self):
    return self.misbehavior >= 100

  def attempt_connection(self, sock=None):
    """ Attempts a connection if it is appropriate.
        Returns True if a successful connection is made
        Otherwise returns False

        If a sock is provided then that socket is used for the connection.
        If the connection is unsuccessful the socket is returned untouched.
    """

    # Check that we have enough room for a new connection.
    if not self.spore.outbound_sockets_semaphore.acquire(blocking=False):
      if sock:
        # TODO: do this properly.
        sock.sendall("We're full")
        sock.shutdown(SHUT_RDWR)
        sock.close()
      return False

    # Check if this peer is banned.
    if self.is_banned():
      self.spore.outbound_sockets_semaphore.release()
      if sock:
        sock.shutdown()
        sock.close()
      return False

    with self.socket_lock:
      if self.socket is not None:
        # We already have a socket, therefore we are already connected.
        self.spore.outbound_sockets_semaphore.release()
        # TODO: increase misbehaving.
        return False

      # Try connecting.
      try:
        if sock:
          self.socket = sock
        else:
          self.socket = socket.create_connection(self.address)
      except ConnectionRefusedError:
        self.misbehavior += 30
        self.spore.outbound_sockets_semaphore.release()
        return False

      # Run the on_connect handler threads in series.
      for func in self.spore.on_connect_handlers:
        try:
          func(self)
        except:
          traceback.print_exc()

      # Okay, we are connected, start this peer's main thread.
      self.recv_loop_thread = threading.Thread(target=self.recv_loop)
      self.recv_loop_thread.start()
      return True


  def disconnect(self):
    # TODO: handle socket errors
    with self.socket_lock:
      if self.socket is not None:
        
        # catch remote shutdown
        try:
          self.socket.shutdown(socket.SHUT_RDWR)
        except OSError as e:
          if e.errno != 107: # errno.ENOTCONN
            raise e
        
        self.socket.close()
        self.socket = None


        # Run the on_disconnect handler threads in series.
        for func in self.spore.on_disconnect_handlers:
          try:
            func(self)
          except:
            traceback.print_exc()

        # FIXME: This part doesn't appear to be working
        #
        #current_thread = threading.current_thread()
        #if self.recv_loop_thread and current_thread != self.recv_loop_thread:
        #  self.recv_loop_thread.join()
        #  self.recv_loop_thread = None

  def _recv(self, amount):
    data = []
    while amount > 0:
      segment = self.socket.recv(amount)
      if segment == b'':
        return None
      amount -= len(segment)
      data.append(segment)
    return b''.join(data)

  def recv_loop(self):
    # This should only be called once per peer..
    assert self.recv_lock.acquire(blocking=False)
    self.recv_lock.release()
    with self.recv_lock:
      while True:
        # FIXME: self.socket could become None at any time...
        try:
          if self.socket:
            data = self._recv(4)
          else:
            data = None
          if data:
            length = int.from_bytes(data,'big')
            # TODO: check that length is not too long for our purposes.
            data = self._recv(length)
        except ConnectionResetError:
          self.disconnect()
          break
        if data is None:
          # We still don't know if we closed it or they did, so disconnect just
          # in case.
          self.disconnect()
          break
        message = Message()
        message.ParseFromString(data)
        funclist = self.spore.handlers.get(message.method)
        if funclist is None:
          # TODO: decide whether or not to throw misbehaving here.
          pass
        else:
          for func in funclist:
            try:
              func(self, message.payload)
            except:
              traceback.print_exc()


class Spore(object):

  def __init__(self, seeds=[], address=None):

    # Session id
    self.nonce = random.randint(0,2**32-1)

    # Reference to the main accept and connect threads.
    self.accept_thread = None
    self.connect_thread = None

    # Boolean representing if the server is running.
    self.running = False

    # The socket that this instance is listening on.
    self.server = None

    # The address that the server should listen on as a (host, port) tuple.
    self.address = address

    # Handlers of messages for this instance.
    self.handlers = collections.defaultdict(list)
    self.on_connect_handlers = []
    self.on_disconnect_handlers = []

    # Dictionary mapping (host, port) -> peer.
    self.peers = {}
    for addr in seeds:
      self.peers[addr] = Peer(self, addr)

    # Lock for the peers dictionary.
    self.peers_lock = threading.Lock()

    # Semaphore to limit the number of connections.
    # TODO: add inbound socket semaphore, currently all connections use this outbound one.
    self.outbound_sockets_semaphore = threading.BoundedSemaphore(MAX_OUTBOUND_CONNECTIONS)


    """
    @self.handler('spore_peerlist')
    def peerlist(peer, payload):

      # TODO: make type checking/validation of data easier.

      for address in payload:
        # TODO: make an Address class that autoserializes.
        addr = Address(address).t
        if (addr not in self.peers) and addr != self.address:
          # TODO: cache these based on their compact representation, not their
          # string representation
          # TODO: broadcast less frequently, not for every peer.
          self.peers[addr] = Peer(self, addr)
          self.broadcast('spore_peerlist',[address])
    """
    @self.handler('peer')
    def recvpeer(peer, data):
      peerfixme = PeerFixme()
      peerfixme.ParseFromString(data)
      ipstr = socket.inet_ntoa(peerfixme.ip)
      address = (ipstr, peerfixme.port)
      with self.peers_lock:
        if address not in self.peers:
          self.peers[address] = Peer(self, address)

    @self.handler('info')
    def recvinfo(peer, data):
      info = Info()
      info.ParseFromString(data)
      if info.nonce == self.nonce:
        peer.disconnect()
      else:
        if info.HasField('port'):
          peerfixme = PeerFixme()
          peerfixme.ip = socket.inet_aton(socket.gethostbyname(peer.address[0]))
          peerfixme.port = info.port
          self.broadcast('peer',peerfixme.SerializeToString())

    @self.on_connect
    def sendinfo(peer):
      info = Info(version=0,nonce=self.nonce)
      if address:
        info.port = address[1]
      peer.send('info', info.SerializeToString())

  def connect_loop(self):
    """ Loops around the peer list once per second looking for peers to connect
        to, if we need to """

    while self.running:
      # Acquire and release this semaphore so that we're not continually
      # creating an array of all peers whilst we're sufficiently connected.
      if not self.outbound_sockets_semaphore.acquire(timeout=0.1):
        continue
      self.outbound_sockets_semaphore.release()

      peer = None

      with self.peers_lock:
        # TODO: make this loop more efficient by maining a peer list that is
        # actually a list. The throttling per IP is another thing altogether.
        peers = self.peers.items()
        if len(peers) != 0:
          addr, peer = random.choice(list(peers))
      if peer:
        peer.attempt_connection()
      time.sleep(0.1)

  def incoming_connection_handler(self, socket, address):
    """ Handler for an outbound socket to a peer """
    self.peers_lock.acquire()
    if address not in self.peers:
      self.peers[address] = Peer(self, address)
    peer = self.peers[address]
    self.peers_lock.release()

    peer.attempt_connection(socket)

  def accept_loop(self):
    """ Listens for new connections """
    self.server = socket.socket()
    # NOTE: there should be a way to get this to work without this option...
    self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.server.bind(self.address)
    self.server.listen(8)
    while self.running:
      try:
        sock, address = self.server.accept()
      except OSError as e:
        if e.errno == 22: # Server shutdown
          break
        print("Socket error during accept: " + str(e))
        time.sleep(1)
        continue
      threading.Thread(target=self.incoming_connection_handler, args=(sock, address)).start()
    
  def random_peer(self):
    """ Returns a random peer """
    peers = self.all_connected_peers()
    if len(peers) > 0:
        return random.choice(peers)
    return None

  def all_connected_peers(self):
    """ Returns a list of connected peers """
    ret = []
    self.peers_lock.acquire()
    for address, peer in self.peers.items():
      if peer.is_connected():
        ret.append(peer)
    self.peers_lock.release()
    return ret

  def num_connected_peers(self):
    """ Returns the number of connected peers """
    return len(self.all_connected_peers())

  def handler(self, method):
    def wrapper(func):
      self.handlers[method].append(func)
    return wrapper

  def on_connect(self, func):
    self.on_connect_handlers.append(func)

  def on_disconnect(self, func):
    self.on_disconnect_handlers.append(func)

  def broadcast(self, method, payload):
    """ Broadcasts data as a json object to all connected peers """
    with self.peers_lock:
      for addr, peer in self.peers.items():
        if peer.is_connected():
          # FIXME: peer might become disconnected =/
          peer.send(method, payload)

  def run(self):
    self.running = True
    self.connect_thread = threading.Thread(target=self.connect_loop)
    self.connect_thread.start()
    if self.address:
      self.accept_thread = threading.Thread(target=self.accept_loop)
      self.accept_thread.start()

    try:
      if self.address:
        self.accept_thread.join()
      self.connect_thread.join()
    except KeyboardInterrupt:
      print("Received keyboard interrupt, shutting down...")
      self.shutdown()

  def shutdown(self):
    # Set conditions to stop the accept/connect threads:
    self.running = False

    if self.accept_thread:
      self.server.shutdown(socket.SHUT_RDWR)
      self.server.close()
      self.server = None
      self.accept_thread.join()
    self.connect_thread.join()

    # Disconnect all peers:
    with self.peers_lock:
      for addr, peer in self.peers.items():
        peer.disconnect()
