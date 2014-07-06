import unittest
# from spore import rlp
import threading
from spore import Spore
import sys
import time
import random

def run_in_own_thread(spore):
    threading.Thread(target=spore.run).start()
    time.sleep(0.01)

class TestThreading(unittest.TestCase):

    def test_threading(self):
        time.sleep(0.02)
        started = threading.active_count()
        port = random.randint(10000, 60000)
        server = Spore(seeds=[], address=('127.0.0.1', port), source_ip='127.0.0.1')
        run_in_own_thread(server)
        time.sleep(0.02)
        self.assertTrue(threading.active_count() > started)
        server.shutdown()
        # TODO: work out why shutdown needs to pause -- it shouldn't =/
        time.sleep(0.01)
        self.assertEqual(threading.active_count(), started)

    def test_two_threading(self):
        time.sleep(0.05)
        started = threading.active_count()
        port = random.randint(10000, 60000)
        server = Spore(seeds=[], address=('127.0.0.1', port), source_ip='127.0.0.1')
        run_in_own_thread(server)
        ac = threading.active_count()
        self.assertTrue(ac > started)
        client = Spore(seeds=[('127.0.0.1',port)])
        run_in_own_thread(client)
        self.assertTrue(threading.active_count() > ac)
        server.shutdown()
        client.shutdown()
        # TODO: work out why shutdown needs to pause -- it shouldn't =/
        time.sleep(0.01)
        self.assertEqual(threading.active_count(), started)

class TestEverything(unittest.TestCase):

    def setUp(self):
        """ Create a client and server, and run them in their own threads. """
        self.port = random.randint(10000, 60000)
        self.server = Spore(address=('127.0.0.1', self.port), source_ip='127.0.0.1')
        self.client = Spore(seeds=[('127.0.0.1', self.port)], source_ip='127.0.0.2')
        run_in_own_thread(self.server)
        run_in_own_thread(self.client)

    def tearDown(self):
        self.server.shutdown()
        self.client.shutdown()

    def test_connection(self):
        time.sleep(0.01)

        # Check they're connected.
        self.assertEqual(self.client.num_connected_peers(), 1)
        self.assertEqual(self.server.num_connected_peers(), 1)

        # shut them down.
        self.server.shutdown()
        self.client.shutdown()

        # test they're not connected.
        self.assertEqual(self.server.num_connected_peers(), 0)
        self.assertEqual(self.client.num_connected_peers(), 0)

        # apparently this shit needs to sleep for a second
        # TODO: bonus points for working out why this is.
        time.sleep(0.01)

        # and this is the only running thread.
        self.assertEqual(threading.active_count(), 1)

        # start them up again
        run_in_own_thread(self.server)
        run_in_own_thread(self.client)

        # sleep 10ms for connection.
        time.sleep(0.01)

        # make sure they're connected again.
        self.assertEqual(self.client.num_connected_peers(), 1)
        self.assertEqual(self.server.num_connected_peers(), 1)

    # TODO: def test_max_connections(self):
    # Test the connection queue.

    def test_graceful_illegal_shutdown(self):
        blah = Spore()
        class MockStdout:
            def write(self, data):
                pass
        stderr = sys.stderr
        sys.stderr = MockStdout() # This is to silence the error message.
        blah.shutdown()
        sys.stderr = stderr

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
        new_client = Spore(seeds=[('127.0.0.1', self.port)], source_ip='127.0.0.3')
        run_in_own_thread(new_client)
        time.sleep(0.01)
        self.assertTrue(on_connect_called)
        new_client.shutdown()
        time.sleep(0.01)
        self.assertTrue(on_disconnect_called)

    def test_messages(self):
        client_received_message = False
        server_received_message = False

        # Checks encoding.
        PAYLOAD_FOR_SERVER = b'test2'
        PAYLOAD_FOR_CLIENT = b'test1'

        @self.server.on_message('client_to_server')
        def client_to_server(peer, payload):
            nonlocal server_received_message
            self.assertEqual(payload, PAYLOAD_FOR_SERVER)
            server_received_message = True

        @self.client.on_message('server_to_client')
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
        new_clients = [Spore(seeds=[('127.0.0.1', self.port)],
                             address=('127.0.0.'+str(3+i), self.port+i+1),
                             source_ip='127.0.0.'+str(3+i)) for i in range(9)]
        for new_client in new_clients:
            run_in_own_thread(new_client)

        try:
            failed = 0

            for client in [self.client] + new_clients:
                while client.num_connected_peers() != 10:
                    time.sleep(0.01)
                    failed += 1
                    # wait for at most one second on this test.
                    self.assertLess(failed, 100)

            time.sleep(0.01)

            for client in [self.client] + new_clients:
                self.assertEqual(client.num_connected_peers(), 10)

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
        self.server.broadcast('anybroadcast', b'some data')
        self.client = Spore(seeds=[('127.0.0.1', self.port)], source_ip='127.0.0.2')
        run_in_own_thread(self.client)
        self.server.broadcast('test',b'test')
        self.server.broadcast('test',b'test')

    def test_repeat_connections(self):
        counter = 0
        TIMES_RUN = 10
        failed = 0
        for i in range(TIMES_RUN):
            self.client.shutdown()

            self.client = Spore(seeds=[('127.0.0.1', self.port)], source_ip='127.0.0.2')

            hit = False

            @self.client.on_message('test_in')
            def test_in_handler(node, payload):
                nonlocal counter, hit
                if payload == b'1' and not hit:
                    counter += 1
                    hit = True

            run_in_own_thread(self.client)
            while not hit:
                time.sleep(0.01)
                self.server.broadcast('test_in', b'1')

                # wait for at most two seconds on this test.
                failed += 1
                self.assertLess(failed, 200)

        self.assertEqual(counter, TIMES_RUN)

    def test_large_packets(self):
        payload_test = b'\x00' * 1024
        payload_recv = None

        @self.server.on_message('test_large_packets')
        def recPackets(node, payload):
            nonlocal payload_recv
            payload_recv = payload

        self.client.broadcast('test_large_packets', payload_test)
        for _ in range(200):
            time.sleep(0.01) # wait for at most 2 seconds for payload_recv
            if payload_recv:
                break
        self.assertEqual(payload_test, payload_recv)

    def test_ban_self(self):
        duplicate = Spore(seeds=[('127.0.0.1',self.port)])
        duplicate._nonce = self.server._nonce # fake this part. this breaks abstraction :(
        run_in_own_thread(duplicate)
        try:
            self.assertEqual(duplicate.num_connected_peers(), 0)
        finally:
            duplicate.shutdown()

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
