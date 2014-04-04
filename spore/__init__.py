import json
from . import rlp
import traceback
import collections
import random
import signal
import sys
import socket
import threading
import time

MAX_OUTBOUND_CONNECTIONS = 8
MAX_INBOUND_CONNECTIONS = 8

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

  def send(self, method, payload=b''):
    # TODO: handle socket error
    with self.send_lock:
      self.socket.sendall(rlp.encode([method.encode('utf-8'), payload]))

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
      return False

    # Check if this peer is banned.
    if self.is_banned():
      self.spore.outbound_sockets_semaphore.release()
      return False

    with self.socket_lock:
      if self.socket is not None:
        # We already have a socket, therefore we are already connected.
        self.spore.outbound_sockets_semaphore.release()
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
        self.socket.shutdown(socket.SHUT_RDWR)
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

  def recv_loop(self):
    # This should only be called once per peer..
    assert self.recv_lock.acquire(blocking=False)
    self.recv_lock.release()
    with self.recv_lock:
      while True:
        data = rlp.recv(self.socket)
        if data is None:
          # We still don't know if we closed it or they did, so disconnect just
          # in case.
          self.disconnect()
          break
        method, payload = data
        funclist = self.spore.handlers.get(method.decode('utf-8'))
        if funclist is None:
          # TODO: decide whether or not to throw misbehaving here.
          pass
        else:
          for func in funclist:
            try:
              func(self, payload)
            except:
              traceback.print_exc()


class Spore(object):

  def __init__(self, seeds=[], address=None):

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
    self.server.listen(MAX_INBOUND_CONNECTIONS)
    self.server.settimeout(0.1)
    while self.running:
      try:
        sock, address = self.server.accept()
      except socket.timeout:
        continue
      threading.Thread(target=self.incoming_connection_handler, args=(sock, address)).start()
    self.server.shutdown(socket.SHUT_WR)
    self.server.close()
    self.server = None

  def num_connected_peers(self):
    """ Returns the number of connected peers """
    count = 0
    self.peers_lock.acquire()
    for address, peer in self.peers.items():
      if peer.is_connected():
        count += 1
    self.peers_lock.release()
    return count

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
      self.accept_thread.join()
    self.connect_thread.join()

    # Disconnect all peers:
    with self.peers_lock:
      for addr, peer in self.peers.items():
        peer.disconnect()
