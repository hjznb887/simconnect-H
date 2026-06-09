import ctypes
import unittest

import simconnect_native as scn


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


def _packet_with_payload(payload):
    size = scn.SIMOBJECT_DATA_HEADER_SIZE + ctypes.sizeof(payload)
    buf = ctypes.create_string_buffer(size)
    header = ctypes.cast(buf, ctypes.POINTER(scn.SIMOBJECT_DATA_HEADER)).contents
    header.dwID = scn.SIMCONNECT_RECV_ID_SIMOBJECT_DATA
    header.dwSize = size
    header.dwRequestID = 42
    ctypes.memmove(
        ctypes.addressof(buf) + scn.SIMOBJECT_DATA_HEADER_SIZE,
        ctypes.byref(payload),
        ctypes.sizeof(payload),
    )
    return ctypes.cast(buf, ctypes.POINTER(scn.SIMCONNECT_RECV))


class SimConnectNativeTests(unittest.TestCase):
    def test_import_exports_version(self):
        self.assertEqual(scn.__version__, "0.3.1")
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

    @unittest.skipIf(hasattr(ctypes, "WinDLL"), "Non-Windows fallback only")
    def test_load_dll_has_clear_error_without_windll(self):
        simconnect = scn.SimConnect()

        with self.assertRaisesRegex(OSError, "ctypes.WinDLL"):
            simconnect.load_dll("SimConnect.dll")


if __name__ == "__main__":
    unittest.main()
