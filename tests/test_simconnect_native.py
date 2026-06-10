import ctypes
import unittest

import simconnect_native as scn
from simconnect_native.registry import VarSlot


class _FakeDll:
    def __init__(self):
        self.calls = []

    def SimConnect_RequestDataOnSimObject(self, *args):
        self.calls.append(("request", args))
        return 0

    def SimConnect_RequestDataOnSimObjectType(self, *args):
        self.calls.append(("request_type", args))
        return 0

    def SimConnect_AddToDataDefinition(self, *args):
        self.calls.append(("add_definition", args))
        return 0

    def SimConnect_SetDataOnSimObject(self, *args):
        self.calls.append(("set_data", args))
        return 0

    def SimConnect_TransmitClientEvent(self, *args):
        self.calls.append(("transmit_event", args))
        return 0


def _packet_with_payload(payload, msg_id=scn.SIMCONNECT_RECV_ID_SIMOBJECT_DATA):
    size = scn.SIMOBJECT_DATA_PAYLOAD_OFFSET + ctypes.sizeof(payload)
    buf = ctypes.create_string_buffer(size)
    header = ctypes.cast(buf, ctypes.POINTER(scn.SIMOBJECT_DATA_HEADER)).contents
    header.dwSize = size
    header.dwVersion = 1
    header.dwID = msg_id
    header.dwRequestID = 42
    header.dwDefineCount = 1
    ctypes.memmove(
        ctypes.addressof(buf) + scn.SIMOBJECT_DATA_PAYLOAD_OFFSET,
        ctypes.byref(payload),
        ctypes.sizeof(payload),
    )
    return ctypes.cast(buf, ctypes.POINTER(scn.SIMCONNECT_RECV))


class SimConnectNativeTests(unittest.TestCase):
    def test_import_exports_version(self):
        self.assertEqual(scn.__version__, "0.5.0")
        self.assertTrue(hasattr(scn, "SimConnect"))

    def test_read_data_accepts_exported_ctypes_datatype_constants(self):
        p_data = _packet_with_payload(ctypes.c_double(123.5))

        value = scn.SimConnect.read_data(p_data, scn.SIMCONNECT_DATATYPE_FLOAT64)

        self.assertEqual(value, 123.5)

    def test_read_double_returns_request_id_and_value(self):
        p_data = _packet_with_payload(ctypes.c_double(87.25))

        request_id, value = scn.SimConnect().read_double(p_data)

        self.assertEqual(request_id, 42)
        self.assertEqual(value, 87.25)

    def test_read_double_rejects_header_only_packet(self):
        buf = ctypes.create_string_buffer(scn.SIMOBJECT_DATA_HEADER_SIZE)
        header = ctypes.cast(buf, ctypes.POINTER(scn.SIMOBJECT_DATA_HEADER)).contents
        header.dwSize = scn.SIMOBJECT_DATA_HEADER_SIZE
        header.dwVersion = 1
        header.dwID = scn.SIMCONNECT_RECV_ID_SIMOBJECT_DATA
        header.dwRequestID = 42
        header.dwDefineCount = 0
        p_data = ctypes.cast(buf, ctypes.POINTER(scn.SIMCONNECT_RECV))

        request_id, value = scn.SimConnect().read_double(p_data)

        self.assertEqual(request_id, 42)
        self.assertIsNone(value)

    def test_api_methods_accept_exported_ctypes_constants(self):
        fake_dll = _FakeDll()
        simconnect = scn.SimConnect()
        simconnect._dll = fake_dll
        simconnect._hSimConnect = scn.HANDLE(1)

        simconnect.add_to_data_definition(
            1,
            b"PLANE ALTITUDE",
            b"Feet",
            datatype=scn.SIMCONNECT_DATATYPE_FLOAT64,
            datasize=scn.SIMCONNECT_UNUSED,
        )
        simconnect.request_data_on_simobject(
            1,
            1,
            object_id=scn.SIMCONNECT_OBJECT_ID_USER,
            period=scn.SIMCONNECT_PERIOD_SECOND,
        )
        simconnect.request_data_on_simobject_type(
            1,
            1,
            simobject_type=scn.SIMCONNECT_SIMOBJECT_TYPE_USER,
        )
        simconnect.transmit_client_event(
            object_id=scn.SIMCONNECT_OBJECT_ID_USER,
            event_id=100,
        )

        self.assertEqual(
            [name for name, _args in fake_dll.calls],
            ["add_definition", "request", "request_type", "transmit_event"],
        )

    def test_subscribe_dispatch_routes_simobject_data(self):
        received = []
        simconnect = scn.SimConnect()
        simconnect._subscriptions[7] = {
            "slot": VarSlot(7, b"PLANE ALTITUDE", b"Feet", 4, True),
            "callback": received.append,
            "period": scn.SIMCONNECT_PERIOD_SECOND,
            "multi": False,
        }
        simconnect._DispatchProc = ctypes.WINFUNCTYPE(
            None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
        )
        simconnect._refresh_dispatch_wrapper()

        p_data = _packet_with_payload(ctypes.c_double(1500.0))
        ctypes.cast(p_data, ctypes.POINTER(scn.SIMOBJECT_DATA_HEADER)).contents.dwRequestID = 7
        simconnect._dispatch_cb(p_data, 0, None)

        self.assertEqual(received, [1500.0])

    def test_subscribe_dispatch_routes_bytype_messages(self):
        received = []
        simconnect = scn.SimConnect()
        simconnect._subscriptions[3] = {
            "slot": VarSlot(3, b"AIRSPEED INDICATED", b"Knots", 4, True),
            "callback": received.append,
            "period": scn.SIMCONNECT_PERIOD_SECOND,
            "multi": False,
        }
        simconnect._DispatchProc = ctypes.WINFUNCTYPE(
            None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
        )
        simconnect._refresh_dispatch_wrapper()

        p_data = _packet_with_payload(ctypes.c_double(120.0), scn.SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE)
        header = ctypes.cast(p_data, ctypes.POINTER(scn.SIMOBJECT_DATA_HEADER)).contents
        header.dwRequestID = 3
        simconnect._dispatch_cb(p_data, 0, None)

        self.assertEqual(received, [120.0])

    def test_assigned_object_id_parsed_at_correct_offset(self):
        buf = ctypes.create_string_buffer(20)
        header = ctypes.cast(buf, ctypes.POINTER(scn.SIMCONNECT_RECV)).contents
        header.dwSize = 20
        header.dwVersion = 1
        header.dwID = 12  # SIMCONNECT_RECV_ID_ASSIGNED_OBJECT_ID
        ctypes.cast(
            ctypes.addressof(buf) + 12, ctypes.POINTER(scn.DWORD),
        ).contents.value = 99
        ctypes.cast(
            ctypes.addressof(buf) + 16, ctypes.POINTER(scn.DWORD),
        ).contents.value = 12345
        p_data = ctypes.cast(buf, ctypes.POINTER(scn.SIMCONNECT_RECV))

        obj_id = scn.SimConnect()._parse_assigned_object_id(p_data)

        self.assertEqual(obj_id, 12345)

    def test_open_defers_subscription_apply_until_open_message(self):
        class FakeDll:
            def __init__(self):
                self.clears = 0
                self.adds = 0
                self.requests = 0

            def SimConnect_ClearDataDefinition(self, *_a):
                self.clears += 1
                return 0

            def SimConnect_AddToDataDefinition(self, *_a):
                self.adds += 1
                return 0

            def SimConnect_RequestDataOnSimObject(self, *_a):
                self.requests += 1
                return 0

            def SimConnect_RequestDataOnSimObjectType(self, *_a):
                self.requests += 1
                return 0

        fake = FakeDll()
        sc = scn.SimConnect()
        sc._DispatchProc = ctypes.WINFUNCTYPE(
            None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
        )
        sc._dll = fake
        sc._hSimConnect = scn.HANDLE(1)
        sc._open_received = False
        sc.subscribe("PLANE ALTITUDE", "feet", lambda _v: None)
        self.assertEqual(fake.adds, 0)
        self.assertEqual(fake.requests, 0)

        open_buf = ctypes.create_string_buffer(12)
        open_hdr = ctypes.cast(open_buf, ctypes.POINTER(scn.SIMCONNECT_RECV)).contents
        open_hdr.dwSize = 12
        open_hdr.dwVersion = 1
        open_hdr.dwID = scn.SIMCONNECT_RECV_ID_OPEN
        p_open = ctypes.cast(open_buf, ctypes.POINTER(scn.SIMCONNECT_RECV))
        sc._refresh_dispatch_wrapper()
        sc._dispatch_cb(p_open, 0, None)

        self.assertTrue(sc._open_received)
        self.assertEqual(fake.adds, 1)
        self.assertGreaterEqual(fake.requests, 1)

    def test_dispatch_wrapper_installed_without_subscriptions(self):
        sc = scn.SimConnect()
        sc._DispatchProc = ctypes.WINFUNCTYPE(
            None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
        )
        sc._refresh_dispatch_wrapper()
        self.assertIsNotNone(sc._dispatch_cb)

        open_buf = ctypes.create_string_buffer(12)
        open_hdr = ctypes.cast(open_buf, ctypes.POINTER(scn.SIMCONNECT_RECV)).contents
        open_hdr.dwSize = 12
        open_hdr.dwVersion = 1
        open_hdr.dwID = scn.SIMCONNECT_RECV_ID_OPEN
        p_open = ctypes.cast(open_buf, ctypes.POINTER(scn.SIMCONNECT_RECV))
        sc._dispatch_cb(p_open, 0, None)
        self.assertTrue(sc._open_received)

    def test_connect_uses_working_config_index(self):
        class FakeDll:
            def __init__(self):
                self.opens = []

            def SimConnect_Open(self, ph_sim, app_name, *_rest):
                idx = _rest[-1]
                if hasattr(idx, "value"):
                    idx = int(idx.value)
                else:
                    idx = int(idx)
                self.opens.append(idx)
                if idx < 2:
                    return 0x80004005
                target = getattr(ph_sim, "_obj", ph_sim)
                target.value = 99
                return 0

            def SimConnect_SubscribeToSystemEvent(self, *_a):
                return 0

            def SimConnect_CallDispatch(self, *_a):
                return 0

        sc = scn.SimConnect()
        sc._DispatchProc = ctypes.WINFUNCTYPE(
            None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
        )
        sc._dll = FakeDll()
        sc.connect("TestApp", config_indices=(0, 1, 2), wait_open=False, start_dispatch=False)
        self.assertEqual(sc._config_index, 2)
        self.assertTrue(sc.is_open)

    @unittest.skipIf(hasattr(ctypes, "WinDLL"), "Non-Windows fallback only")
    def test_load_dll_has_clear_error_without_windll(self):
        simconnect = scn.SimConnect()

        with self.assertRaisesRegex(OSError, "ctypes.WinDLL"):
            simconnect.load_dll("SimConnect.dll")


if __name__ == "__main__":
    unittest.main()
