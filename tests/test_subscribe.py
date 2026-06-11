"""Subscription HRESULT and lifecycle tests."""
import ctypes
import unittest

import simconnect_native as scn
from simconnect_native.constants import TYPE_REQ_OFFSET


class SubscribeHresultTests(unittest.TestCase):
    _E_INVALIDARG = 0x80070057

    class _FakeDll:
        fail_on = ""

        def SimConnect_AddToDataDefinition(self, *_args):
            if self.fail_on == "add":
                return SubscribeHresultTests._E_INVALIDARG
            return 0

        def SimConnect_ClearDataDefinition(self, *_args):
            return 0

        def SimConnect_RequestDataOnSimObject(self, *_args):
            if self.fail_on == "request":
                return SubscribeHresultTests._E_INVALIDARG
            return 0

        def SimConnect_RequestDataOnSimObjectType(self, *_args):
            if self.fail_on == "request_type":
                return SubscribeHresultTests._E_INVALIDARG
            return 0

        def SimConnect_CallDispatch(self, *_args):
            return 0

    def _client(self, fail_on: str = ""):
        sc = scn.SimConnect()
        sc._DispatchProc = ctypes.WINFUNCTYPE(
            None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
        )
        dll = self._FakeDll()
        dll.fail_on = fail_on
        sc._dll = dll
        sc._hSimConnect = scn.HANDLE(1)
        sc._open_received = True
        return sc

    def test_subscribe_raises_on_request_data_failure(self):
        sc = self._client(fail_on="request")
        with self.assertRaises(scn.SimConnectError) as ctx:
            sc.subscribe("PLANE ALTITUDE", "feet", lambda _v: None)
        self.assertIn("RequestDataOnSimObject", str(ctx.exception))

    def test_subscribe_raises_on_request_type_failure(self):
        sc = self._client(fail_on="request_type")
        with self.assertRaises(scn.SimConnectError) as ctx:
            sc.subscribe("PLANE ALTITUDE", "feet", lambda _v: None)
        self.assertIn("RequestDataOnSimObjectType", str(ctx.exception))

    def test_subscribe_many_raises_on_add_definition_failure(self):
        sc = self._client(fail_on="add")
        with self.assertRaises(scn.SimConnectError) as ctx:
            sc.subscribe_many(
                {"alt": ("PLANE ALTITUDE", "feet")},
                lambda _d: None,
            )
        self.assertIn("AddToDataDefinition", str(ctx.exception))

    def test_subscribe_rejects_negative_period(self):
        sc = self._client()
        with self.assertRaises(ValueError):
            sc.subscribe("PLANE ALTITUDE", "feet", lambda _v: None, period=-1)

    def test_close_clears_defined_slots(self):
        sc = self._client()
        slot = sc._registry.get_or_create_var("PLANE ALTITUDE", "feet")
        slot.defined = True
        sc.close()
        self.assertFalse(slot.defined)


if __name__ == "__main__":
    unittest.main()
