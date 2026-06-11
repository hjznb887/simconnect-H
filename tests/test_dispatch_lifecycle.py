"""Background dispatch stop/restart, health APIs, paused dispatch."""
import ctypes
import threading
import time
import unittest

import simconnect_native as scn


class _FakeDll:
    block_dispatch = threading.Event()
    call_count = 0

    def SimConnect_CallDispatch(self, _h, _cb, _ctx):
        type(self).call_count += 1
        if not self.block_dispatch.wait(timeout=0.05):
            return 0
        while self.block_dispatch.is_set():
            time.sleep(0.01)
        return 0

    def SimConnect_AddToDataDefinition(self, *_a):
        return 0

    def SimConnect_RequestDataOnSimObject(self, *_a):
        return 0

    def SimConnect_ClearDataDefinition(self, *_a):
        return 0

    def SimConnect_Close(self, *_a):
        return 0


def _client():
    sc = scn.SimConnect()
    sc._DispatchProc = ctypes.WINFUNCTYPE(
        None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
    )
    sc._dll = _FakeDll()
    sc._hSimConnect = scn.HANDLE(1)
    sc._open_received = True
    sc.set_dispatch_cb(lambda *_: None)
    return sc


class DispatchLifecycleTests(unittest.TestCase):
    def test_stop_returns_false_when_thread_stuck(self):
        sc = _client()
        sc._dll.block_dispatch.set()
        sc.start_background_dispatch()
        time.sleep(0.05)
        self.assertTrue(sc.dispatch_thread_alive)

        stopped = sc.stop_background_dispatch(timeout=0.1)
        self.assertFalse(stopped)
        self.assertTrue(sc.dispatch_zombie)
        self.assertIsNotNone(sc._dispatch_thread)
        sc._dll.block_dispatch.clear()

    def test_restart_force_starts_new_thread_after_zombie(self):
        sc = _client()
        sc._dll.block_dispatch.set()
        sc.start_background_dispatch()
        old = sc._dispatch_thread
        sc.stop_background_dispatch(timeout=0.05, force=True)
        sc.restart_background_dispatch(force=True)
        self.assertTrue(sc._dispatch_running)
        self.assertIsNotNone(sc._dispatch_thread)
        self.assertIsNot(old, sc._dispatch_thread)
        sc._dll.block_dispatch.clear()
        sc.stop_background_dispatch(timeout=1.0, force=True)

    def test_is_dataflow_healthy_requires_recent_callback(self):
        sc = _client()
        sc.start_background_dispatch()
        self.assertTrue(sc.is_dataflow_healthy())  # 无订阅时仅检查 dispatch
        sc._subscriptions[1] = {"slot": object()}
        self.assertFalse(sc.is_dataflow_healthy())
        sc.touch_subscription_callback()
        self.assertTrue(sc.is_dataflow_healthy(max_stale=2.0))
        sc.stop_background_dispatch(timeout=1.0)

    def test_with_paused_dispatch_restarts(self):
        sc = _client()
        sc.start_background_dispatch()
        with sc.with_paused_dispatch(restart=True, stop_timeout=1.0, force=True):
            self.assertFalse(sc._dispatch_running)
        self.assertTrue(sc._dispatch_running)
        sc.stop_background_dispatch(timeout=1.0, force=True)


class GetWithBackgroundDispatchTests(unittest.TestCase):
    class _PumpDll:
        def __init__(self):
            self.dispatch_calls = 0

        def SimConnect_AddToDataDefinition(self, *_a):
            return 0

        def SimConnect_ClearDataDefinition(self, *_a):
            return 0

        def SimConnect_RequestDataOnSimObjectType(self, *_a):
            return 0

        def SimConnect_CallDispatch(self, *_a):
            self.dispatch_calls += 1
            return 0

    def test_get_does_not_pump_when_background_dispatch_running(self):
        sc = scn.SimConnect()
        sc._DispatchProc = ctypes.WINFUNCTYPE(
            None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
        )
        dll = self._PumpDll()
        sc._dll = dll
        sc._hSimConnect = scn.HANDLE(1)
        sc._open_received = True
        sc._dispatch_running = True
        sc.set_dispatch_cb(lambda *_: None)
        slot = sc._registry.get_or_create_var("PLANE ALTITUDE", "feet")
        slot.defined = True

        def run_get():
            try:
                sc.get("PLANE ALTITUDE", "feet", timeout=0.05)
            except scn.SimConnectTimeoutError:
                pass

        t = threading.Thread(target=run_get)
        t.start()
        t.join(timeout=1.0)
        self.assertEqual(dll.dispatch_calls, 0)


if __name__ == "__main__":
    unittest.main()
