from spore import Spore
import uuid
import sys

# Get the ports as arguments (for easy local testing)
my_port   = int(sys.argv[1])
seed_port = int(sys.argv[2])

# Create this node
node = Spore(seeds=[('127.0.0.1', seed_port)], address=('127.0.0.1', my_port))

# Global seen, so we don't broadcast messages ad infinitum
seen = {}

@node.handler
def chat(peer, params):
  if params['uuid'] not in seen:
    seen[params['uuid']] = True
    print(params['nick'].rjust(30) + " : " + params['message'])
    node.broadcast('chat', params)

node.start()

nick = input("What's your nick? ")

try:
  while True:
    message = input("Message: ")
    print("You".rjust(30) + " : " + message)
    uid = str(uuid.uuid4())
    seen[uid] = True
    node.broadcast('chat', {'message': message,
                            'nick': nick,
                            'uuid': uid} )
finally:
  node.stop()
