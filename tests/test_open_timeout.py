"""Open timeout, native hung, IsolatedSimConnect kill."""
import time
import unittest

import simconnect_native as scn
from simconnect_native.isolated import IsolatedSimConnect, _hang_forever


class _SlowOpenDll:
    def SimConnect_Open(self, *_a):
        time.sleep(30)
        return 0

    def SimConnect_Close(self, *_a):
        return 0

    def SimConnect_CallDispatch(self, *_a):
        return 0


class OpenTimeoutTests(unittest.TestCase):
    def test_open_timeout_raises_and_marks_hung(self):
        sc = scn.SimConnect(auto_reconnect=True)
        sc._dll = _SlowOpenDll()
        with self.assertRaises(scn.SimConnectOpenTimeoutError):
            sc.open("App", timeout=0.15)
        self.assertTrue(sc._native_hung)
        self.assertFalse(sc._auto_reconnect)
        with self.assertRaises(scn.SimConnectNativeHungError):
            sc.open("App", timeout=0.1)

    def test_connect_hard_disables_reconnect(self):
        sc = scn.SimConnect(auto_reconnect=True)
        sc._dll = _SlowOpenDll()
        with self.assertRaises(scn.SimConnectOpenTimeoutError):
            sc.connect_hard("App", open_timeout=0.15, timeout=0.1, wait_open=False)
        self.assertFalse(sc._auto_reconnect)


class IsolatedKillTests(unittest.TestCase):
    def test_kill_unblocks_parent_when_worker_hangs(self):
        iso = IsolatedSimConnect(
            heartbeat_timeout=2.0,
            worker_target=_hang_forever,
        )
        t0 = time.monotonic()
        with self.assertRaises(scn.SimConnectOpenTimeoutError):
            iso.connect("App", open_timeout=0.2, timeout=0.1)
        elapsed = time.monotonic() - t0
        self.assertLess(elapsed, 4.0)
        self.assertFalse(iso.worker_alive)
        iso.kill()


if __name__ == "__main__":
    unittest.main()
