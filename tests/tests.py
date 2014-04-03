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

    def test_messages(self):
        self.client_received_message = False
        self.server_received_message = False

        # Checks encoding.
        MAGIC_FOR_SERVER = {'true':['1234','false']}
        MAGIC_FOR_CLIENT = {'4321':['false']}

        @self.server.handler
        def client_to_server(peer, params):
            self.assertEqual(params['magic_for_server'], MAGIC_FOR_SERVER)
            self.server_received_message = True

        @self.client.handler
        def server_to_client(peer, params):
            self.assertEqual(params['magic_for_client'], MAGIC_FOR_CLIENT)
            self.client_received_message = True

        self.server.broadcast('client_to_server', {'magic_for_server': MAGIC_FOR_SERVER})
        self.client.broadcast('server_to_client', {'magic_for_client': MAGIC_FOR_CLIENT})
        time.sleep(0.1)
        self.assertFalse(self.client_received_message)
        self.assertFalse(self.server_received_message)

        self.server.broadcast('server_to_client', {'magic_for_client': MAGIC_FOR_CLIENT})
        self.client.broadcast('client_to_server', {'magic_for_server': MAGIC_FOR_SERVER})
        time.sleep(0.1)
        self.assertTrue(self.client_received_message)
        self.assertTrue(self.server_received_message)


if __name__ == '__main__':
    unittest.main()
