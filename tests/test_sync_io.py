import ctypes
import threading
import unittest

import simconnect_native as scn
from simconnect_native.constants import TYPE_REQ_OFFSET
from simconnect_native.registry import Registry, VarSlot


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


class RegistryTests(unittest.TestCase):
    def test_get_or_create_var_reuses_slot(self):
        reg = Registry()
        a = reg.get_or_create_var("PLANE ALTITUDE", "Feet")
        b = reg.get_or_create_var("plane altitude", "Feet")
        self.assertIs(a, b)
        self.assertGreaterEqual(a.define_id, Registry._VAR_ID_START)

    def test_event_ids_are_stable(self):
        reg = Registry()
        id1, _ = reg.get_event_id("AP_MASTER")
        id2, _ = reg.get_event_id("ap_master")
        self.assertEqual(id1, id2)


class SyncIOTests(unittest.TestCase):
    class _FakeDll:
        def SimConnect_RequestDataOnSimObject(self, *_args):
            return 0

        def SimConnect_RequestDataOnSimObjectType(self, *_args):
            return 0

        def SimConnect_AddToDataDefinition(self, *_args):
            return 0

        def SimConnect_ClearDataDefinition(self, *_args):
            return 0

        def SimConnect_CallDispatch(self, *_args):
            return 0

    def _client(self):
        sc = scn.SimConnect()
        sc._DispatchProc = ctypes.WINFUNCTYPE(
            None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
        )
        sc._dll = self._FakeDll()
        sc._hSimConnect = scn.HANDLE(1)
        sc._open_received = True
        return sc

    def test_get_returns_value_from_dispatch(self):
        sc = self._client()
        slot = sc._registry.get_or_create_var("PLANE ALTITUDE", "Feet")
        slot.defined = True

        result = {}

        def worker():
            result["value"] = sc.get("PLANE ALTITUDE", "Feet", timeout=1.0)

        t = threading.Thread(target=worker)
        t.start()

        for _ in range(100):
            if not t.is_alive():
                break
            with sc._lock:
                pending = sc._pending_get.get(slot.define_id)
            if pending and not pending["event"].is_set():
                type_req = slot.define_id + TYPE_REQ_OFFSET
                sc._dispatch_sync_responses(_packet(ctypes.c_double(5000.0), type_req))
            t.join(timeout=0.02)

        t.join(timeout=1.0)
        self.assertEqual(result.get("value"), 5000.0)

    def test_get_timeout_raises(self):
        sc = self._client()
        slot = sc._registry.get_or_create_var("PLANE ALTITUDE", "Feet")
        slot.defined = True
        with self.assertRaises(scn.SimConnectTimeoutError):
            sc.get("PLANE ALTITUDE", "Feet", timeout=0.05)


class EventsTests(unittest.TestCase):
    def test_trigger_maps_once(self):
        calls = []

        class FakeDll:
            def SimConnect_MapClientEventToSimEvent(self, *_a):
                calls.append("map")
                return 0

            def SimConnect_TransmitClientEvent(self, *_a):
                calls.append("transmit")
                return 0

        sc = scn.SimConnect()
        sc._dll = FakeDll()
        sc._hSimConnect = scn.HANDLE(1)
        sc.trigger("AP_MASTER")
        sc.trigger("AP_MASTER")
        self.assertEqual(calls, ["map", "transmit", "transmit"])


class SubscribeLifecycleTests(unittest.TestCase):
    def test_unsubscribe_stops_callbacks(self):
        sc = scn.SimConnect()
        sc._DispatchProc = ctypes.WINFUNCTYPE(
            None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
        )
        received = []
        sc._subscriptions[2] = {
            "slot": VarSlot(2, b"PLANE ALTITUDE", b"Feet", 4, True),
            "callback": received.append,
            "period": scn.SIMCONNECT_PERIOD_SECOND,
            "multi": False,
        }
        sc._refresh_dispatch_wrapper()
        sc.unsubscribe(2)
        sc._dispatch_subscriptions(_packet(ctypes.c_double(1.0), 2))
        self.assertEqual(received, [])

    def test_subscribe_many_delivers_dict(self):
        sc = scn.SimConnect()
        sc._DispatchProc = ctypes.WINFUNCTYPE(
            None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
        )
        received = []
        sc._subscriptions[5] = {
            "slot": VarSlot(5, b"", b"", 4, True),
            "callback": received.append,
            "period": scn.SIMCONNECT_PERIOD_SECOND,
            "multi": True,
            "fields": [
                ("alt", "PLANE ALTITUDE", "Feet", 4),
                ("ias", "AIRSPEED INDICATED", "Knots", 4),
            ],
            "field_layout": [("alt", 4, 0), ("ias", 4, 8)],
        }
        sc._refresh_dispatch_wrapper()
        payload = (ctypes.c_double * 2)(12000.0, 250.0)
        sc._dispatch_subscriptions(_packet(payload, 5))
        self.assertEqual(received, [{"alt": 12000.0, "ias": 250.0}])


if __name__ == "__main__":
    unittest.main()
