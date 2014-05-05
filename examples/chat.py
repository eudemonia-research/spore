import threading
import uuid
import sys

from spore import Spore

from encodium import *

# the Field class comes from encodium and allows for nice serialization.
class ChatMessage(Field):

  def fields():
    message = Bytes()
    nick = Bytes()
    uid = Bytes()

# Get the ports as arguments (for easy local testing)
my_port   = int(sys.argv[1])
seed_port = int(sys.argv[2])

# Create this node
me = Spore(seeds=[('127.0.0.1', seed_port)], address=('127.0.0.1', my_port))

# Global seen, so we don't broadcast messages ad infinitum
seen = {}

@me.handler('chat')
def chat(peer, payload):
  chat_message = ChatMessage.make(payload)
  message = chat_message.message
  nick = chat_message.nick
  uid = chat_message.uid
  if uid not in seen:

    # Mark it as seen
    seen[uid] = True

    # print the message
    print(nick.rjust(30), ":", message)

    # Relay this message to other peers
    me.broadcast('chat', payload)

# Start it in it's own thread.
threading.Thread(target=me.run).start()

nick = input("What's your nick? ").encode()

print("Type messages to send to the network and press enter.")

try:
  while True:
    message = input().encode()
    uid = uuid.uuid4().bytes
    seen[uid] = True
    me.broadcast('chat', ChatMessage.make(message=message, uid=uid, nick=nick))
finally:
  me.shutdown()
