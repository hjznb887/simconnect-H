import ctypes
import unittest

import simconnect_native as scn
from simconnect_native.constants import (
    SIMCONNECT_CLIENT_EVENT_SIMSTART,
    SIMCONNECT_RECV_ID_EVENT,
)
from simconnect_native.structures import SIMCONNECT_RECV, SIMCONNECT_RECV_EVENT


def _event_packet(event_id: int, data: int = 0):
    buf = ctypes.create_string_buffer(ctypes.sizeof(SIMCONNECT_RECV_EVENT))
    evt = ctypes.cast(buf, ctypes.POINTER(SIMCONNECT_RECV_EVENT)).contents
    evt.dwSize = ctypes.sizeof(SIMCONNECT_RECV_EVENT)
    evt.dwVersion = 1
    evt.dwID = SIMCONNECT_RECV_ID_EVENT
    evt.uEventID = event_id
    evt.dwData = data
    return ctypes.cast(buf, ctypes.POINTER(SIMCONNECT_RECV))


class SystemEventsTests(unittest.TestCase):
    class _FakeDll:
        def __init__(self):
            self.calls = []

        def SimConnect_SubscribeToSystemEvent(self, *_a):
            self.calls.append("subscribe")
            return 0

    def test_subscribe_system_event_dispatches(self):
        sc = scn.SimConnect()
        sc._dll = self._FakeDll()
        sc._hSimConnect = scn.HANDLE(1)
        sc._init_system_events()
        received = []

        event_id = sc.subscribe_system_event("Pause", lambda n, d: received.append((n, d)))
        self.assertGreaterEqual(event_id, 90100)
        sc._dispatch_system_events(_event_packet(event_id, 1))
        self.assertEqual(received, [("Pause", 1)])

    def test_subscribe_simstart_uses_internal_id(self):
        sc = scn.SimConnect()
        sc._dll = self._FakeDll()
        sc._hSimConnect = scn.HANDLE(1)
        sc._init_system_events()
        received = []
        event_id = sc.subscribe_system_event(
            "SimStart", lambda n, d: received.append((n, d)),
        )
        self.assertEqual(event_id, SIMCONNECT_CLIENT_EVENT_SIMSTART)
        sc._dispatch_system_events(_event_packet(event_id, 2))
        self.assertEqual(received, [("SimStart", 2)])

    def test_unsubscribe_system_event(self):
        sc = scn.SimConnect()
        sc._dll = self._FakeDll()
        sc._hSimConnect = scn.HANDLE(1)
        sc._init_system_events()
        received = []
        event_id = sc.subscribe_system_event("SimStop", received.append)
        self.assertTrue(sc.unsubscribe_system_event(event_id))
        sc._dispatch_system_events(_event_packet(event_id))
        self.assertEqual(received, [])


class GetManyIdTests(unittest.TestCase):
    def test_get_many_id_disjoint_from_subscription_ids(self):
        from simconnect_native.registry import Registry

        reg = Registry()
        sub_ids = [reg.alloc_subscription_id() for _ in range(5)]
        get_id = reg.alloc_get_many_id()
        self.assertGreaterEqual(get_id, 20000)
        self.assertNotIn(get_id, sub_ids)


if __name__ == "__main__":
    unittest.main()
