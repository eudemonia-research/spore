import unittest
# from spore import rlp
import threading
from spore import Spore
import time
import random

class TestThreading(unittest.TestCase):

    def test_threading(self):
        started = threading.active_count()
        port = random.randint(10000, 60000)
        server = Spore(seeds=[], address=('127.0.0.1', port))
        threading.Thread(target=server.run).start()
        time.sleep(0.15)
        self.assertTrue(threading.active_count() > started)
        server.shutdown()
        time.sleep(0.15)
        self.assertEqual(threading.active_count(), started)

    def test_two_threading(self):
        started = threading.active_count()
        port = random.randint(10000, 60000)
        server = Spore(seeds=[], address=('127.0.0.1', port))
        threading.Thread(target=server.run).start()
        time.sleep(0.15)
        ac = threading.active_count()
        self.assertTrue(ac > started)
        client = Spore(seeds=[('127.0.0.1',port)])
        threading.Thread(target=client.run).start()
        time.sleep(0.15)
        self.assertTrue(threading.active_count() > ac)
        server.shutdown()
        time.sleep(0.15)
        client.shutdown()
        time.sleep(0.15)
        self.assertEqual(threading.active_count(), started)

class TestNetworking(unittest.TestCase):

    def setUp(self):
        """ Create a client and server, and run them in their own threads. """
        self.port = random.randint(10000, 60000)
        self.server = Spore(seeds=[], address=('127.0.0.1', self.port))
        self.client = Spore(seeds=[('127.0.0.1', self.port)])
        threading.Thread(target=self.server.run).start()
        threading.Thread(target=self.client.run).start()
        # Sleep for 150ms to give them time to connect
        time.sleep(0.15)

    def tearDown(self):
        self.server.shutdown()
        self.client.shutdown()
        # Sleep for 150ms to give them time to shutdown
        time.sleep(0.15)

    def test_connection(self):

        #print("Test that they are connected to each other.")
        self.assertEqual(self.client.num_connected_peers(), 1)
        self.assertEqual(self.server.num_connected_peers(), 1)

        #print("Stop them")
        self.server.shutdown()
        self.client.shutdown()

        #print("Sleep for 150ms let them clean up")
        time.sleep(0.15)

        #print("Test that they are no longer connected to each other.")
        self.assertEqual(self.server.num_connected_peers(), 0)
        self.assertEqual(self.client.num_connected_peers(), 0)

        #print("Ensure there are no other threads running.")
        self.assertEqual(threading.active_count(), 1)

        #print("Sleep 150ms")
        time.sleep(0.15)

        #print("Start them again")
        threading.Thread(target=self.server.run).start()
        threading.Thread(target=self.client.run).start()

        #print("Sleep again")
        time.sleep(0.15)

        #print("Test that they are connected to each other.")
        self.assertEqual(self.client.num_connected_peers(), 1)
        self.assertEqual(self.server.num_connected_peers(), 1)

    # TODO: def test_max_connections(self):
    # Test the connection queue.

    def test_graceful_illegal_shutdown(self):
        blah = Spore()
        blah.shutdown()

    def test_on_connect(self):
        on_connect_called = False
        on_disconnect_called = False
        @self.server.on_connect
        def do_one_thing(peer):
            nonlocal on_connect_called
            peer.send('some_data')
            on_connect_called = True
        @self.server.on_disconnect
        def do_one_thing(peer):
            nonlocal on_disconnect_called
            on_disconnect_called = True
        new_client = Spore(seeds=[('127.0.0.1', self.port)])
        threading.Thread(target=new_client.run).start()
        time.sleep(0.1)
        self.assertTrue(on_connect_called)
        time.sleep(0.1)
        new_client.shutdown()
        time.sleep(0.1)
        self.assertTrue(on_disconnect_called)

    def test_messages(self):
        client_received_message = False
        server_received_message = False

        # Checks encoding.
        PAYLOAD_FOR_SERVER = b'test2'
        PAYLOAD_FOR_CLIENT = b'test1'

        @self.server.handler('client_to_server')
        def client_to_server(peer, payload):
            nonlocal server_received_message
            self.assertEqual(payload, PAYLOAD_FOR_SERVER)
            server_received_message = True

        @self.client.handler('server_to_client')
        def server_to_client(peer, payload):
            nonlocal client_received_message
            self.assertEqual(payload, PAYLOAD_FOR_CLIENT)
            client_received_message = True

        self.server.broadcast('client_to_server', PAYLOAD_FOR_SERVER)
        self.client.broadcast('server_to_client', PAYLOAD_FOR_CLIENT)
        time.sleep(0.1)
        self.assertFalse(client_received_message)
        self.assertFalse(server_received_message)

        self.server.broadcast('server_to_client', PAYLOAD_FOR_CLIENT)
        self.client.broadcast('client_to_server', PAYLOAD_FOR_SERVER)
        time.sleep(0.1)
        self.assertTrue(client_received_message)
        self.assertTrue(server_received_message)

    def test_peerlist(self):
        new_clients = [Spore(seeds=[('127.0.0.1', self.port)],address=('127.0.0.1', self.port+1+i)) for i in range(9)]
        for new_client in new_clients:
            threading.Thread(target=new_client.run).start()
        # Wait for a while because things need to propagate.
        time.sleep(15)
        try:
            self.assertEqual(self.client.num_connected_peers(), 10)
        finally:
            for new_client in new_clients:
                new_client.shutdown()

    ''' TODO: this test
    def test_overload(self):
        new_clients = [Spore(seeds=[('127.0.0.1', self.port)],address=('127.0.0.1', self.port+1+i)) for i in range(9)]
        for new_client in new_clients:
            threading.Thread(target=new_client.run).start()
        # Wait for a while because things need to propagate.
        time.sleep(20)
        try:
            self.assertEqual(self.client.num_connected_peers(), 10)
        finally:
            for new_client in new_clients:
                new_client.shutdown()
    '''

    '''
    # Not using Protobufs anymore, going with encodium.
    def test_protobufs(self):
        called = False
        class MockProtobuf(object):
            def __init__(self):
                x=1234
            def ParseFromString(self, data):
                nonlocal called
                called=True
        @self.client.handler('test', MockProtobuf)
        def donothing(peer, obj):
            self.assertEqual(obj.x, 1234)
        self.server.broadcast('test', b'this gets ignored')
        time.sleep(0.2)
        self.assertTrue(called)
    '''

    def test_broadcast(self):
        self.client.shutdown()
        time.sleep(0.1)
        #print('should see 3 broadcasts:')
        #print('broadcast1')
        self.server.broadcast('anybroadcast', b'some data')
        time.sleep(0.1)
        self.client = Spore(seeds=[('127.0.0.1', self.port)])
        threading.Thread(target=self.client.run).start()
        time.sleep(0.1)
        #print('broadcast2')
        self.server.broadcast('test',b'test')
        time.sleep(0.1)
        #print('broadcast3')
        self.server.broadcast('test',b'test')
        time.sleep(0.1)
        # this will either finish or not - locking erbytesror
        # no asserts
        
    def test_repeatConnections(self):
        counter = 0
        times_run = 10
        for i in range(times_run):
            self.client.shutdown()
            time.sleep(0.1)
            self.client = Spore(seeds=[('127.0.0.1', self.port)])

            @self.client.handler('test_in')
            def test_in_handler(node, payload):
                nonlocal counter
                if payload == b'1':
                    counter += 1
                    
            threading.Thread(target=self.client.run).start()
            time.sleep(0.1)
            self.server.broadcast('test_in', b'1')
            time.sleep(0.1)
            
        self.assertEqual(counter, times_run)
        
    def test_large_packets(self):
        payload_test = b'\x00' * 1024
        payload_recv = None
        
        @self.server.handler('test_large_packets')
        def recPackets(node, payload):
            nonlocal payload_recv
            payload_recv = payload
            
        self.client.broadcast('test_large_packets', payload_test)
        time.sleep(0.1)
        self.assertEqual(payload_test, payload_recv)

'''
class TestRLP(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_encode(self):
        encoded = rlp.encode([ [], [[]], [ [], [[]] ] ])
        self.assertEqual(encoded, bytes([ 0xc7, 0xc0, 0xc1, 0xc0, 0xc3, 0xc0, 0xc1, 0xc0 ]))

        encoded = rlp.encode([b'cat',b'dog'])
        self.assertEqual(encoded, bytes([ 0xc8, 0x83 ]) + b'cat' + bytes([0x83]) + b'dog')

        # Empty string.
        self.assertEqual(rlp.encode(b''), bytes([ 0x80 ]))

        # Empty list.
        self.assertEqual(rlp.encode([]), bytes([ 0xc0 ]))

        # b'\x0f'
        self.assertEqual(rlp.encode(b'\x0f'), bytes([0x0f]))
        
        big_list = [ [ b'\x00' * 1024 ] * 1024 ]
        self.assertEqual(rlp.decode(rlp.encode(big_list)), big_list)

        data = b'Lorem ipsum dolor sit amet, consectetur adipisicing elit'
        encoded = rlp.encode(data)
        decoded = rlp.decode(encoded)
        self.assertEqual(data, decoded)
'''

if __name__ == '__main__':
    unittest.main()
