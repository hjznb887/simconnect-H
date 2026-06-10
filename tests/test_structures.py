import ctypes
import unittest

import simconnect_native as scn


class StructureLayoutTests(unittest.TestCase):
    def test_simconnect_recv_layout_matches_msfs_sdk(self):
        self.assertEqual(ctypes.sizeof(scn.SIMCONNECT_RECV), 12)
        self.assertEqual(scn.SIMOBJECT_DATA_HEADER_SIZE, 44)
        self.assertEqual(scn.SIMOBJECT_DATA_PAYLOAD_OFFSET, 40)
        self.assertEqual(scn.SIMCONNECT_RECV_ID_SIMOBJECT_DATA, 8)
        self.assertEqual(scn.SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE, 9)


if __name__ == "__main__":
    unittest.main()
