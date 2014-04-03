import unittest
import threading
from spore import Spore
import time
import random

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

    def test_on_connect(self):
        on_connect_called = False
        on_disconnect_called = False
        @self.server.on_connect
        def do_one_thing(peer):
            nonlocal on_connect_called
            peer.send('some_data','')
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
        MAGIC_FOR_SERVER = {'true':['1234','false']}
        MAGIC_FOR_CLIENT = {'4321':['false']}

        @self.server.handler
        def client_to_server(peer, params):
            nonlocal server_received_message
            self.assertEqual(params['magic_for_server'], MAGIC_FOR_SERVER)
            server_received_message = True

        @self.client.handler
        def server_to_client(peer, params):
            nonlocal client_received_message
            self.assertEqual(params['magic_for_client'], MAGIC_FOR_CLIENT)
            client_received_message = True

        self.server.broadcast('client_to_server', {'magic_for_server': MAGIC_FOR_SERVER})
        self.client.broadcast('server_to_client', {'magic_for_client': MAGIC_FOR_CLIENT})
        time.sleep(0.1)
        self.assertFalse(client_received_message)
        self.assertFalse(server_received_message)

        self.server.broadcast('server_to_client', {'magic_for_client': MAGIC_FOR_CLIENT})
        self.client.broadcast('client_to_server', {'magic_for_server': MAGIC_FOR_SERVER})
        time.sleep(0.1)
        self.assertTrue(client_received_message)
        self.assertTrue(server_received_message)


if __name__ == '__main__':
    unittest.main()
