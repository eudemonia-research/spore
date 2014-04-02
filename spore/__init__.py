import json
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
    self.recv_loop_thread = None
    self.send_lock = threading.Lock()
    self.socket_lock = threading.Lock()
    self.spore = spore
    self.socket = None
    self.address = address
    self.misbehavior = misbehavior

  def send(self, method, params):
    # TODO: handle socket error
    # TODO: send RLP object instead of JSON
    message = {'method':method,'params':params}
    with self.send_lock:
      self.socket.sendall(json.dumps(message).encode('utf-8') + b'\n')

  def _recv(self):
    # TODO: handle socket error
    # TODO: recv use RLP instead of JSON
    data = b''
    while not data.endswith(b'\n'):
      byte = self.socket.recv(1)
      if not byte:
        return
      data += byte
    ret = json.loads(data.decode('utf-8'))
    # FIXME: fix this recv + recv loop logic
    #        (can send a "null" message atm)
    assert ret is not None
    return ret

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
      #except OSError as e:
      #  # Can't connect. Not necessarily misbehaving, but depending on why we
      #  # couldn't connect, maybe we want to say this node doesn't exist.
      #  # For now just print it out.
      #  print("Couldn't connect to " + str(self.address))
      #  print(str(e))
      #  self.spore.outbound_sockets_semaphore.release()
      #  return False 
      except ConnectionRefusedError:
        self.misbehavior += 30
        self.spore.outbound_sockets_semaphore.release()
        return False

      # Okay, we are connected. Start this peer's thread and return.
      self.recv_loop_thread = threading.Thread(target=self.recv_loop)
      self.recv_loop_thread.start()
      return True


  def disconnect(self):
    # TODO: handle socket errors
    with self.socket_lock:
      if self.socket is not None:
        print("Disconnecting " + str(self.socket))
        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()
        self.socket = None

        # FIXME: This part doesn't appear to be working
        #
        #current_thread = threading.current_thread()
        #if self.recv_loop_thread and current_thread != self.recv_loop_thread:
        #  self.recv_loop_thread.join()
        #  self.recv_loop_thread = None

  def recv_loop(self):
    while True:
      print("About to recv from " + str(self.socket))
      message = self._recv()
      print("Returned from recv from " + str(self.socket))
      if not message:
        # We still don't know if we closed it or they did, so disconnect just
        # in case.
        self.disconnect()
        break
      # TODO: RLP encoding instead of JSON
      func = self.spore.handlers.get(message['method'], None)
      if func:
        func(self, message['params'])


class Spore(object):

  def __init__(self, seeds=[], address=None):
    self.accept_thread = None
    self.connect_thread = None

    self.running = False
    self.server = None
    self.address = address
    self.handlers = {}
    self.peers = {}
    for addr in seeds:
      self.peers[addr] = Peer(self, addr)
    self.peers_lock = threading.Lock()
    # TODO: add inbound socket semaphore, currently all connections use this one.
    self.outbound_sockets_semaphore = threading.BoundedSemaphore(MAX_OUTBOUND_CONNECTIONS)

  def connect_loop(self):
    """ Loops around the peer list once per second looking for peers to connect
        to, if we need to """

    while self.running:
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
    self.server.settimeout(1)
    while self.running:
      try:
        sock, address = self.server.accept()
      except socket.timeout:
        continue
      threading.Thread(target=self.incoming_connection_handler, args=(sock, address)).start()
    self.server.shutdown(socket.SHUT_WR)
    self.server.close()

  def num_connected_peers(self):
    """ Returns the number of connected peers """
    count = 0
    self.peers_lock.acquire()
    for address, peer in self.peers.items():
      if peer.is_connected():
        count += 1
    self.peers_lock.release()
    return count

  def handler(self, func):
    self.handlers[func.__name__] = func

  def broadcast(self, method, params):
    """ Broadcasts data as a json object to all connected peers """
    with self.peers_lock:
      for addr, peer in self.peers.items():
        peer.send(method, params)

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
