import json
import signal
import sys
import socket
import threading
import time

MAX_OUTBOUND_CONNECTIONS = 8
MAX_INBOUND_CONNECTIONS = 8

# TODO: release connection semaphores when the connections die.
# TODO: synchronization wrappers
# TODO: move all connection logic (semaphores etc) into Peer class.

class Peer(object):

  def __init__(self, spore, address, connection=None, misbehavior=0):
    self.spore = spore 
    self.connection = connection
    self.address = address
    self.misbehavior = misbehavior

  def send(self, method, params):
    # TODO: handle socket error
    # TODO: send RLP object instead of JSON
    message = {'method':method,'params':params}
    self.connection.sendall(json.dumps(message).encode('utf-8') + b'\n')

  def recv(self):
    # TODO: handle socket error
    # TODO: recv use RLP instead of JSON
    data = b''
    while not data.endswith(b'\n'):
      byte = self.connection.recv(1)
      if not byte:
        return
      data += byte
    return json.loads(data.decode('utf-8'))

  def is_banned(self):
    return self.misbehavior >= 100

  def is_connected(self):
    return self.connection is not None

  def connect(self):
    assert self.connection is None
    self.connection = socket.create_connection(self.address)
    # TODO: handle socket error better.

  def disconnect(self):
    # TODO: handle socket error
    self.connection.shutdown()
    self.connection.close()
    self.connection = None

  def recv_loop(self):
    while True:
      message = self.recv()
      if not message:
        return
      # TODO: RLP encoding instead of JSON
      func = self.spore.handlers.get(message['method'], None)
      if func:
        func(self, message['params'])


class Spore(object):

  def __init__(self, seeds=[], address=None):
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

    while True:
      self.outbound_connections_semaphore.acquire()

      connected = False

      self.peers_lock.acquire()
      for addr, peer in self.peers.items():
        if not peer.is_connected() and not peer.is_banned():
          try:
            peer.connect()
            connected = True
            threading.Thread(target=peer.recv_loop).start()
            break
          except ConnectionRefusedError:
            peer.connection = None
            peer.misbehavior += 30
      self.peers_lock.release()

      if not connected:
        self.outbound_connections_semaphore.release()

      time.sleep(1)

  def incoming_connection_handler(self, connection, address):
    """ Handler for an outbound connection to a peer """
    self.peers_lock.acquire()
    if address not in self.peers:
      self.peers[address] = Peer(self, address)
    peer = self.peers[address]
    self.peers_lock.release()

    # TODO: check if we are already connected to this peer
    #       and increase misbehaving if we are
    if peer.connection is not None:
      peer.connection.close()
      peer.connection = None
    assert peer.connection is None
    peer.connection = connection

    peer.recv_loop()

  def accept_loop(self):
    """ Listens for connections """
    self.server = socket.socket()
    self.server.bind(self.address)
    self.server.listen(MAX_INBOUND_CONNECTIONS)
    while True:
      self.inbound_connections_semaphore.acquire()
      connection, address = self.server.accept()
      threading.Thread(target=self.incoming_connection_handler, args=(connection, address)).start()

  def handler(self, func):
    self.handlers[func.__name__] = func

  def broadcast(self, method, params):
    """ Broadcasts data as a json object to all connected peers """
    self.peers_lock.acquire()
    for addr, peer in self.peers.items():
      peer.send(method, params)
    self.peers_lock.release()

  def start(self):
    self.threads = [threading.Thread(target=self.connect_loop)]
    if self.address:
      self.threads.append(threading.Thread(target=self.accept_loop))
    for thread in self.threads:
      thread.start()

  def stop(self):
    self.peers_lock.acquire()
    for addr, peer in self.peers.items():
      peer.disconnect()
    self.peers_lock.release()
    for thread in self.threads:
      thread.stop()
    self.server.shutdown()
    self.server.close()
