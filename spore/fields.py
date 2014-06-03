from encodium import *
import socket

def prefix_length(data):
    length = len(data)
    if length < 0xfa:
        return bytes([length]) + data
    encoded_length = length.to_bytes()
    return bytes([len(encoded_length)+0xf9]) + encoded_length + data

def encode_data(data_array):
    ret = []
    for data in data_array:
        ret.append(prefix_length(data))
    return b''.join(ret)

def decode_data(data):
    ''' returns the contents of data as an array '''
    ret = []
    i = 0
    while i < len(data):
        length = data[i]
        length_length = 1
        if length >= 0xfa:
            length_length += length - 0xf9
            length = data[i+1:i+length_length]
        ret.append(data[i+length_length:i+length_length+length])
    return ret

class Message(Field):
    @staticmethod
    def fields():
        # TODO: Fix encodium so this is just a string in the standard python address format.
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