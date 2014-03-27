from spore import Spore
import time

# Initialise nodes like this:
lighthouse = Spore(seeds=[], address=('127.0.0.1', 1234))
ship       = Spore(seeds=[('127.0.0.1', 1234)], address=None)

# Define handlers for message types (use the name of the function):
@ship.handler
def beacon(peer, message):
  print("Recevied beacon from " + str(peer.address) + " : " + str(message))
  
  peer.send('beacon_received', 'Thanks!')

# Run in the background:
lighthouse.start()
ship.start()

# Main loop, broadcast beacon message to all peers once per second:
counter = 0
while True:
  lighthouse.broadcast('beacon', counter)
  counter += 1
  time.sleep(1)
