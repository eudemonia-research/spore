import json
import signal
import sys
import socket
import threading
import time

MAX_OUTBOUND_CONNECTIONS = 8
MAX_INBOUND_CONNECTIONS = 8

# TODO: release connection semaphores when the connections die.
# TODO: move all connection logic (semaphores etc) into Peer class.

class Peer(object):

  def __init__(self, spore, address, socket=None, misbehavior=0):
    self.recv_loop_thread = None
    self.send_lock = threading.Lock()
    self.spore = spore 
    self.socket = socket
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
    # TODO: fix this recv + recv loop logic
    assert ret is not None
    return ret

  def is_banned(self):
    return self.misbehavior >= 100

  def is_connected(self):
    return self.socket is not None

  def connect(self):
    assert self.socket is None
    self.socket = socket.create_connection(self.address)
    # TODO: handle socket error better.

  def disconnect(self):
    # TODO: handle socket error
    if self.socket:
      # TODO: concurrency on this peer... move all of this peer's connection logic into this class.
      self.socket.shutdown(socket.SHUT_RDWR)
      self.socket.close()
      self.socket = None

    if self.recv_loop_thread:
      self.recv_loop_thread.join()

  def recv_loop(self):
    while True:
      message = self._recv()
      if not message:
        # We still don't know if we closed it or they did.
        if self.socket:
          self.socket.close()
          self.socket = None
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
    self.outbound_connections_semaphore = threading.BoundedSemaphore(MAX_OUTBOUND_CONNECTIONS)
    self.inbound_connections_semaphore = threading.BoundedSemaphore(MAX_INBOUND_CONNECTIONS)

  def connect_loop(self):
    """ Loops around the peer list once per second looking for peers to connect
        to, if we need to """

    while self.running:
      if not self.outbound_connections_semaphore.acquire(timeout=0.1):
        # check to see if we are still running once a second.
        continue

      connected = False

      with self.peers_lock:
        for addr, peer in self.peers.items():
          if not peer.is_connected() and not peer.is_banned():
            try:
              peer.connect()
              connected = True
              peer.recv_loop_thread = threading.Thread(target=peer.recv_loop).start()
              break
            except ConnectionRefusedError:
              peer.connection = None
              peer.misbehavior += 30

      if not connected:
        self.outbound_connections_semaphore.release()

      time.sleep(0.1)

  def incoming_connection_handler(self, socket, address):
    """ Handler for an outbound connection to a peer """
    self.peers_lock.acquire()
    if address not in self.peers:
      self.peers[address] = Peer(self, address)
    peer = self.peers[address]
    self.peers_lock.release()

    # TODO: check if we are already connected to this peer
    #       and increase misbehaving if we are
    assert peer.socket is None
    peer.socket = socket

    peer.recv_loop_thread = threading.current_thread()
    peer.recv_loop()

  def accept_loop(self):
    """ Listens for connections """
    self.server = socket.socket()
    # NOTE: there should be a way to get this to work without this option...
    self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    self.server.bind(self.address)
    self.server.listen(MAX_INBOUND_CONNECTIONS)
    self.server.settimeout(1)
    while self.running:
      self.inbound_connections_semaphore.acquire()
      try:
        connection, address = self.server.accept()
      except socket.timeout:
        self.inbound_connections_semaphore.release()
        continue
      threading.Thread(target=self.incoming_connection_handler, args=(connection, address)).start()
    #self.server.shutdown(socket.SHUT_WR)
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
