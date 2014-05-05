import threading
import time

from spore import Spore

# Initialise nodes like this:
lighthouse = Spore(seeds=[], address=('127.0.0.1', 1234))
ship       = Spore(seeds=[('127.0.0.1', 1234)], address=None)

# Define handlers for message types (use the name of the function):
@ship.handler('beacon')
def beacon(peer, message):
  print("Recevied beacon from " + str(peer.address) + " : " + str(message))
  peer.send('beacon_received', b'Thanks!')

# Run in the background:
threading.Thread(target=lighthouse.run).start()
threading.Thread(target=ship.run).start()

# Main loop, broadcast beacon message to all peers once per second:
counter = 0
try:
  while True:
    lighthouse.broadcast('beacon', counter.to_bytes(4,'big'))
    counter += 1
    time.sleep(1)
except KeyboardInterrupt:
  lighthouse.shutdown()
  ship.shutdown()
  

