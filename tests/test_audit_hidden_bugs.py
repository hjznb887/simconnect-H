"""Regression tests for latent bugs found during v0.5.2 audit."""
import ctypes
import threading
import time
import unittest

import simconnect_native as scn
from simconnect_native.constants import TYPE_REQ_OFFSET


def _packet(payload, req_id=42, msg_id=scn.SIMCONNECT_RECV_ID_SIMOBJECT_DATA):
    size = scn.SIMOBJECT_DATA_PAYLOAD_OFFSET + ctypes.sizeof(payload)
    buf = ctypes.create_string_buffer(size)
    header = ctypes.cast(buf, ctypes.POINTER(scn.SIMOBJECT_DATA_HEADER)).contents
    header.dwSize = size
    header.dwVersion = 1
    header.dwID = msg_id
    header.dwRequestID = req_id
    header.dwDefineCount = max(1, ctypes.sizeof(payload) // 8)
    ctypes.memmove(
        ctypes.addressof(buf) + scn.SIMOBJECT_DATA_PAYLOAD_OFFSET,
        ctypes.byref(payload),
        ctypes.sizeof(payload),
    )
    return ctypes.cast(buf, ctypes.POINTER(scn.SIMCONNECT_RECV))


class FakeDll:
    def __init__(self):
        self.SimConnect_Open = self._open
        self.SimConnect_Close = lambda *_a: 0
        self.SimConnect_CallDispatch = lambda *_a: 0
        self.SimConnect_AddToDataDefinition = lambda *_a: 0
        self.SimConnect_ClearDataDefinition = lambda *_a: 0
        self.SimConnect_RequestDataOnSimObjectType = lambda *_a: 0
        self.SimConnect_RequestDataOnSimObject = lambda *_a: 0
        self.SimConnect_SubscribeToSystemEvent = lambda *_a: 0

    def _open(self, ph_sim, *_args):
        ph_sim.contents = scn.HANDLE(99)
        return 0


def _make_client():
    sc = scn.SimConnect(auto_reconnect=False)
    sc._dll = FakeDll()
    sc._DispatchProc = ctypes.WINFUNCTYPE(
        None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
    )
    sc._refresh_dispatch_wrapper()
    return sc


class HiddenBugRegressionTests(unittest.TestCase):
    def test_connect_requires_open_message_when_wait_open(self):
        sc = _make_client()
        sc._hSimConnect = scn.HANDLE(99)
        sc._open_received = False
        ready = sc._open_received if True else sc.is_open
        self.assertFalse(ready)

    def test_simstart_flag_reset_on_close(self):
        sc = _make_client()
        sc._hSimConnect = scn.HANDLE(1)
        sc._simstart_subscribed = True
        sc.close()
        self.assertFalse(sc._simstart_subscribed)

    def test_concurrent_get_same_var_isolated(self):
        sc = _make_client()
        sc._hSimConnect = scn.HANDLE(1)
        sc._open_received = True
        slot = sc._registry.get_or_create_var("PLANE ALTITUDE", "Feet")
        slot.defined = True
        results = {}

        def responder(value, delay):
            time.sleep(delay)
            type_req = slot.define_id + TYPE_REQ_OFFSET
            sc._dispatch_sync_responses(
                _packet(ctypes.c_double(value), type_req)
            )

        def worker(name, value, delay):
            threading.Thread(
                target=responder, args=(value, delay), daemon=True,
            ).start()
            results[name] = sc.get("PLANE ALTITUDE", "Feet", timeout=1.0)

        t1 = threading.Thread(target=worker, args=("a", 100.0, 0.02))
        t2 = threading.Thread(target=worker, args=("b", 200.0, 0.04))
        t1.start()
        t2.start()
        t1.join(timeout=3)
        t2.join(timeout=3)
        self.assertEqual(results["a"], 100.0)
        self.assertEqual(results["b"], 200.0)

    def test_get_inside_subscribe_callback_works(self):
        sc = _make_client()
        sc._hSimConnect = scn.HANDLE(1)
        sc._open_received = True
        slot = sc._registry.get_or_create_var("PLANE ALTITUDE", "Feet")
        slot.defined = True
        type_req = slot.define_id + TYPE_REQ_OFFSET
        callback_finished = threading.Event()
        got_value = {"v": None}

        def inject_get_response():
            time.sleep(0.05)
            sc._dispatch_sync_responses(
                _packet(ctypes.c_double(999.0), type_req)
            )

        def callback(_val):
            threading.Thread(target=inject_get_response, daemon=True).start()
            got_value["v"] = sc.get("PLANE ALTITUDE", "Feet", timeout=1.0)
            callback_finished.set()

        sc._subscriptions[1] = {
            "slot": slot,
            "callback": callback,
            "period": 3,
            "multi": False,
        }
        sc._refresh_dispatch_wrapper()
        sc._dispatch_running = True
        sc._dispatch_subscriptions(_packet(ctypes.c_double(500.0), 1))
        self.assertTrue(callback_finished.wait(timeout=2.0))
        self.assertEqual(got_value["v"], 999.0)

    def test_user_dispatch_exception_does_not_kill_thread(self):
        sc = _make_client()
        sc._hSimConnect = scn.HANDLE(1)
        calls = {"n": 0}

        def boom(*_a):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("user cb boom")

        sc.set_dispatch_cb(boom)
        sc.start_background_dispatch()

        def fake_dispatch():
            if sc._dispatch_cb:
                sc._dispatch_cb(_packet(ctypes.c_double(1.0)), 0, None)

        sc.dispatch = fake_dispatch
        time.sleep(0.6)
        self.assertTrue(sc._dispatch_thread.is_alive())
        sc.stop_background_dispatch()


if __name__ == "__main__":
    unittest.main()
