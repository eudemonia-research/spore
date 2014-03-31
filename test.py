import socket


s = socket.socket()
s.bind(('',1234))
s.listen(5)
s.accept()
s.accept()
s.close()

