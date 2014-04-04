class RLPEncodingError(Exception):
    pass

def encode(data):
    if isinstance(data, bytes):
        if len(data) == 1 and data[0] < 0x80:
            return data
        else:
            return encode_length(len(data), 0x80) + data
    elif isinstance(data, list):
        output = b''
        for item in data:
            output += encode(item)
        return encode_length(len(output), 0xc0) + output
    else:
        raise RLPEncodingError("Unknown type: " + str(data.__class__))

def encode_length(length, offset):
    if length < 56:
         return b'' + (length + offset).to_bytes(1,'big')
    elif length < 256**8:
         encoded_length = length.to_bytes((length.bit_length()+7)>>3, 'big')
         return bytes([len(encoded_length) + offset + 55]) + encoded_length
    else:
         raise RLPEncodingError("Input too long")

def recv(socket):
    """ Receives stuff, RLP encoded.
        returns bytes, a list, or None if the connection closed. """
    # TODO: better error messages when data cuts out halfway.
    data = socket.recv(1)
    if not data: return None
    [byte] = data
    if byte < 0x80:
        return data
    if (byte >= 0xb8 and byte < 0xc0) or (byte >= 0xf8):
        data = socket.recv((byte&0x07)+1)
        if not data: return None
        length = int.from_bytes(data,'big')
    else:
        length = (byte & 0x3f)

    if byte < 0xc0:
        # straight up bytes
        # Differentiate between b'' and connection dropped.
        if length == 0: return b''
        data = socket.recv(length)
        if not data: return None
        return data
    else:
        # array
        ret = []
        data = socket.recv(length)
        if not data: return None
        consumed = 0
        while consumed < length:
            obj, sublen = decode(data, consumed)
            consumed += sublen
            ret.append(obj)
        return ret

# Returns object, length
def decode(data, i=0):
    byte = data[i]
    length = 1
    length_length = 0
    if byte < 0x80:
        return bytes([byte]), length
    if (byte >= 0xb8 and byte < 0xc0) or (byte >= 0xf8):
        length_length = (byte&0x07)+1
        length = int.from_bytes(data[i+1:i+1+length_length],'big')
    else:
        length = (byte & 0x3f)

    if byte < 0xc0:
        # straight up bytes
        # Differentiate between b'' and connection dropped.
        x = i+1+length_length
        return data[x:x+length], 1 + length_length + length
    else:
        # array
        ret = []
        consumed = 0
        x = i+1+length_length
        while consumed < length:
            obj, sublen = decode(data, x+consumed)
            consumed += sublen
            ret.append(obj)

        return ret, 1+length_length+length
