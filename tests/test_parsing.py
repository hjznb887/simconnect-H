"""Parsing tests — including MSFS string SimVar layout."""
import ctypes
import struct
import unittest

import simconnect_native as scn
from simconnect_native.constants import SIMCONNECT_DATATYPE_STRINGV_INT
from simconnect_native.parsing import read_data, read_data_at
from simconnect_native.utils import is_string_datatype, unit_for_simconnect_definition


def _packet_with_payload(payload: bytes, req_id: int = 1) -> ctypes.POINTER:
    size = scn.SIMOBJECT_DATA_PAYLOAD_OFFSET + len(payload)
    buf = ctypes.create_string_buffer(size)
    header = ctypes.cast(buf, ctypes.POINTER(scn.SIMOBJECT_DATA_HEADER)).contents
    header.dwSize = size
    header.dwVersion = 1
    header.dwID = scn.SIMCONNECT_RECV_ID_SIMOBJECT_DATA
    header.dwRequestID = req_id
    header.dwDefineCount = 1
    ctypes.memmove(
        scn.SIMOBJECT_DATA_PAYLOAD_OFFSET + ctypes.addressof(buf),
        payload,
        len(payload),
    )
    return ctypes.cast(buf, ctypes.POINTER(scn.SIMCONNECT_RECV))


class ParsingTests(unittest.TestCase):
    def test_msfs_c_string_title(self):
        """MSFS TITLE 等为 null-terminated C 字符串，非 STRINGV 长度前缀。"""
        payload = b"VL3 Asobo\x00" + b"\x00" * 32
        p_data = _packet_with_payload(payload)
        val = read_data(p_data, SIMCONNECT_DATATYPE_STRINGV_INT)
        self.assertEqual(val, "VL3 Asobo")

    def test_stringv_length_prefix_fallback(self):
        """仍支持 SDK STRINGV（int32 长度 + 内容）。"""
        text = b"Hello"
        payload = struct.pack("<i", len(text)) + text
        base = scn.SIMOBJECT_DATA_PAYLOAD_OFFSET
        buf = ctypes.create_string_buffer(base + len(payload))
        ctypes.memmove(base + ctypes.addressof(buf), payload, len(payload))
        addr = ctypes.addressof(buf) + base
        val = read_data_at(addr, SIMCONNECT_DATATYPE_STRINGV_INT)
        self.assertEqual(val, "Hello")

    def test_string_unit_is_null_for_definition(self):
        self.assertTrue(is_string_datatype(11))
        self.assertIsNone(unit_for_simconnect_definition("String", 11))
        self.assertIsNone(unit_for_simconnect_definition("", 11))
        self.assertEqual(unit_for_simconnect_definition("feet", 4), b"feet")

    def test_get_string_dispatch_path(self):
        payload = b"Test Aircraft\x00"
        p_data = _packet_with_payload(payload, req_id=42)
        val = read_data(p_data, SIMCONNECT_DATATYPE_STRINGV_INT)
        self.assertEqual(val, "Test Aircraft")


if __name__ == "__main__":
    unittest.main()
