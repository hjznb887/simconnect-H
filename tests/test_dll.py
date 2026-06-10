import os
import unittest
from unittest.mock import patch

import simconnect_native as scn
import simconnect_native.dll as dll_mod


class DllDiscoveryTests(unittest.TestCase):
    def test_bundled_path_under_package_lib(self):
        expected = os.path.join(
            os.path.dirname(os.path.abspath(dll_mod.__file__)),
            "lib",
            "SimConnect.dll",
        )
        self.assertEqual(scn.bundled_simconnect_dll(), expected)

    def test_env_var_has_highest_priority(self):
        with patch.dict(os.environ, {"SIMCONNECT_DLL": r"C:\Custom\SimConnect.dll"}):
            with patch("simconnect_native.dll.os.path.isfile", return_value=True):
                self.assertEqual(
                    scn.find_simconnect_dll(),
                    r"C:\Custom\SimConnect.dll",
                )

    def test_msfs_install_before_bundled_in_candidates(self):
        candidates = dll_mod.iter_simconnect_dll_candidates()
        bundled = scn.bundled_simconnect_dll()
        msfs_marker = os.path.join("steamapps", "common", "Microsoft Flight Simulator")
        bundled_idx = candidates.index(bundled)
        msfs_idx = next(
            (i for i, p in enumerate(candidates) if msfs_marker.lower() in p.lower()),
            None,
        )
        if msfs_idx is not None:
            self.assertLess(msfs_idx, bundled_idx)

    def test_missing_dll_raises_with_bundled_hint(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SIMCONNECT_DLL", None)
            with patch("simconnect_native.dll.os.path.isfile", return_value=False):
                with self.assertRaises(FileNotFoundError) as ctx:
                    scn.find_simconnect_dll()
                self.assertIn("simconnect_native", str(ctx.exception))
                self.assertIn("lib", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
