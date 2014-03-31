import unittest
import threading
from spore import Spore
import time
import random

class TestNetworking(unittest.TestCase):

    def setUp(self):
        self.port = random.randint(10000, 60000)
        self.lighthouse = Spore(seeds=[], address=('127.0.0.1', self.port))
        self.lighthouse.start()
        self.ship = Spore(seeds=[('127.0.0.1', self.port)])
        self.ship.start()

    def tearDown(self):
        self.lighthouse.stop()
        self.ship.stop()

    def test_connection(self):
        print("Sleep for 100ms to give them time to connect")
        time.sleep(0.1)

        print("Test that they are connected to each other.")
        self.assertEqual(self.ship.num_connected_peers(), 1)
        self.assertEqual(self.lighthouse.num_connected_peers(), 1)

        print("Stop them")
        self.lighthouse.stop()
        self.ship.stop()

        print("Sleep for 100ms let them clean up")
        time.sleep(0.1)

        print("Test that they are no longer connected to each other.")
        self.assertEqual(self.lighthouse.num_connected_peers(), 0)
        self.assertEqual(self.ship.num_connected_peers(), 0)

        print("Ensure there are no other threads running.")
        self.assertEqual(threading.active_count(), 1)

        print("Sleep 100ms")
        time.sleep(0.1)

        print("Start them again")
        self.lighthouse.start()
        self.ship.start()

        print("Sleep again")
        time.sleep(0.1)

        print("Test that they are connected to each other.")
        self.assertEqual(self.ship.num_connected_peers(), 1)
        self.assertEqual(self.lighthouse.num_connected_peers(), 1)

if __name__ == '__main__':
    unittest.main()
