from encodium import Encodium, String, Bytes, Integer


class Message(Encodium):
    method = String.Definition()
    payload = Bytes.Definition()


class Peer(Encodium):
    # TODO: Fix encodium so this is just a string in the standard python address format.
    ip = Bytes.Definition(max_length=16)
    port = Integer.Definition(bits=16, signed=False)


class Info(Encodium):
    version = Integer.Definition(bits=32, signed=False)
    nonce = Integer.Definition(bits=42, signed=False)
    port = Integer.Definition(bits=16, signed=False, optional=True)