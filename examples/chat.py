from spore import Spore
import threading
import uuid
import sys

# Get the ports as arguments (for easy local testing)
my_port   = int(sys.argv[1])
seed_port = int(sys.argv[2])

# Create this node
me = Spore(seeds=[('127.0.0.1', seed_port)], address=('127.0.0.1', my_port))

# Global seen, so we don't broadcast messages ad infinitum
seen = {}

@me.handler('chat')
def chat(peer, payload):
  message, nick, uid = payload
  message = message.decode('utf-8')
  nick = nick.decode('utf-8')
  uid = uid.decode('utf-8')
  if uid not in seen:

    # Mark it as seen
    seen[uid] = True

    # print the message
    print(nick.rjust(30) + " : " + message)

    # Relay this message to other peers
    me.broadcast('chat', payload)

# Start it in it's own thread.
threading.Thread(target=me.run).start()

nick = input("What's your nick? ")

print("Type messages to send to the network and press enter.")

try:
  while True:
    message = input()
    uid = str(uuid.uuid4())
    seen[uid] = True
    me.broadcast('chat', [message.encode('utf-8'),nick.encode('utf-8'),uid.encode('utf-8')])
finally:
  me.shutdown()
