import unittest
import threading
from spore import Spore
import time
import random

class TestNetworking(unittest.TestCase):

    def setUp(self):
        self.port = random.randint(10000, 60000)
        self.server = Spore(seeds=[], address=('127.0.0.1', self.port))
        self.server.start()
        self.client = Spore(seeds=[('127.0.0.1', self.port)])
        self.client.start()

    def tearDown(self):
        self.server.stop()
        self.client.stop()

    def test_connection(self):
        print("Sleep for 100ms to give them time to connect")
        time.sleep(0.1)

        print("Test that they are connected to each other.")
        self.assertEqual(self.client.num_connected_peers(), 1)
        self.assertEqual(self.server.num_connected_peers(), 1)

        print("Stop them")
        self.server.stop()
        self.client.stop()

        print("Sleep for 100ms let them clean up")
        time.sleep(0.1)

        print("Test that they are no longer connected to each other.")
        self.assertEqual(self.server.num_connected_peers(), 0)
        self.assertEqual(self.client.num_connected_peers(), 0)

        print("Ensure there are no other threads running.")
        self.assertEqual(threading.active_count(), 1)

        print("Sleep 100ms")
        time.sleep(0.1)

        print("Start them again")
        self.server.start()
        self.client.start()

        print("Sleep again")
        time.sleep(0.1)

        print("Test that they are connected to each other.")
        self.assertEqual(self.client.num_connected_peers(), 1)
        self.assertEqual(self.server.num_connected_peers(), 1)

if __name__ == '__main__':
    unittest.main()
