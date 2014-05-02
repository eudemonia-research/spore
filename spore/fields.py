from encodium import *
import socket

class Message(Field):
    @staticmethod
    def fields():
        method = String()
        payload = Bytes()

class Peer(Field):
    @staticmethod
    def fields():
        # TODO: Fix encodium so this is just a string in the standard python address format.
        ip = Bytes(max_length=16)
        port = Integer(bits=16, signed=False)


class Info(Field):
    @staticmethod
    def fields():
        version = Integer(bits=32, signed=False)
        nonce = Integer(bits=42, signed=False)
        port = Integer(bits=16, signed=False, optional=True)