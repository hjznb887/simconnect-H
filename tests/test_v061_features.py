"""Tests for mixed subscribe_many and asyncio bridge."""
from __future__ import annotations

import asyncio
import ctypes
import unittest

import simconnect_native as scn
from simconnect_native.constants import (
    SIMCONNECT_DATATYPE_FLOAT64_INT,
    SIMCONNECT_DATATYPE_STRINGV_INT,
    TYPE_REQ_OFFSET,
)
from simconnect_native.registry import VarSlot


class MixedSubscribeTests(unittest.TestCase):
    def test_subscribe_many_composite_unsubscribe(self):
        sc = scn.SimConnect()
        sc._DispatchProc = ctypes.WINFUNCTYPE(
            None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
        )
        received = []
        fields = {
            "alt": ("PLANE ALTITUDE", "feet"),
            "title": ("TITLE", "", SIMCONNECT_DATATYPE_STRINGV_INT),
        }
        sub_id = sc.subscribe_many(fields, received.append)
        self.assertIn(sub_id, sc._composite_subscriptions)
        self.assertEqual(len(sc._composite_subscriptions[sub_id]["children"]), 2)
        self.assertTrue(sc.unsubscribe(sub_id))
        self.assertNotIn(sub_id, sc._composite_subscriptions)

    def test_split_numeric_string_fields(self):
        from simconnect_native.fields import parse_fields, split_numeric_string_fields

        parsed = parse_fields({
            "a": ("PLANE ALTITUDE", "feet"),
            "t": ("TITLE", "", SIMCONNECT_DATATYPE_STRINGV_INT),
        })
        numeric, strings = split_numeric_string_fields(parsed)
        self.assertEqual(len(numeric), 1)
        self.assertEqual(len(strings), 1)
        self.assertEqual(strings[0][0], "t")


class AsyncBridgeTests(unittest.TestCase):
    def test_import_asyncio_module(self):
        from simconnect_native.asyncio import AsyncSimConnect

        self.assertTrue(callable(AsyncSimConnect.connect))

    def test_subscribe_stream_is_async_generator(self):
        from simconnect_native.asyncio import AsyncSimConnect

        async def _check():
            sc = scn.SimConnect()
            loop = asyncio.get_running_loop()
            asc = AsyncSimConnect(sc, loop)
            agen = asc.subscribe_stream({"x": ("PLANE ALTITUDE", "feet")})
            self.assertTrue(hasattr(agen, "__anext__"))
            await asc.close()

        asyncio.run(_check())


if __name__ == "__main__":
    unittest.main()
