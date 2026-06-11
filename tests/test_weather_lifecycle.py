"""Weather API, lifecycle hooks, batch_subscribe tests."""
import ctypes
import threading
import time
import unittest

import simconnect_native as scn
from simconnect_native.registry import VarSlot


class _WeatherFakeDll:
    def __init__(self) -> None:
        self.mode_custom = 0
        self.observations: list = []
        self.sets = 0

    def SimConnect_WeatherSetModeCustom(self, *_a):
        self.mode_custom += 1
        return 0

    def SimConnect_WeatherSetObservation(self, _h, seconds, metar):
        sec = int(getattr(seconds, "value", seconds))
        self.observations.append((sec, metar))
        return 0

    def SimConnect_AddToDataDefinition(self, *_a):
        return 0

    def SimConnect_ClearDataDefinition(self, *_a):
        return 0

    def SimConnect_SetDataOnSimObject(self, *_a):
        self.sets += 1
        return 0

    def SimConnect_CallDispatch(self, *_a):
        return 0

    def SimConnect_Close(self, *_a):
        return 0


def _client(dll=None):
    sc = scn.SimConnect()
    sc._DispatchProc = ctypes.WINFUNCTYPE(
        None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
    )
    sc._dll = dll or _WeatherFakeDll()
    sc._hSimConnect = scn.HANDLE(1)
    sc._open_received = True
    sc.set_dispatch_cb(lambda *_: None)
    return sc


class WeatherApiTests(unittest.TestCase):
    def test_weather_apply_metar_uses_paused_dispatch(self):
        dll = _WeatherFakeDll()
        sc = _client(dll)
        sc.start_background_dispatch()
        time.sleep(0.02)
        metar = b"KSEA 121756Z 18008KT 10SM FEW250 12/06 A3012"
        sc.weather_apply_metar(metar, seconds=1)
        self.assertEqual(len(dll.observations), 1)
        self.assertEqual(dll.observations[0][0], 1)
        self.assertEqual(dll.mode_custom, 1)
        sc.stop_background_dispatch(timeout=2.0, force=True)

    def test_weather_set_ambient_uses_set(self):
        dll = _WeatherFakeDll()
        sc = _client(dll)
        sc.weather_set_ambient(wind_dir=270, temp_c=18)
        self.assertEqual(dll.sets, 2)


class LifecycleHookTests(unittest.TestCase):
    def test_on_sim_start_fires_on_open(self):
        sc = _client()
        fired = []
        sc.on_sim_start = lambda: fired.append(True)
        sc._fire_sim_start_hooks("OPEN")
        self.assertEqual(len(fired), 1)

    def test_batch_subscribe_starts_dispatch(self):
        sc = _client()
        with sc.batch_subscribe():
            sc.set_dispatch_cb(lambda *_: None)
        self.assertTrue(sc._dispatch_running)
        sc.stop_background_dispatch(timeout=2.0, force=True)

    def test_aircraft_change_detection(self):
        sc = _client()
        titles = []
        sc.on_aircraft_changed = titles.append
        sc._subscriptions[1] = {
            "slot": VarSlot(1, b"TITLE", b"", 11, True),
            "callback": sc._on_aircraft_title_update,
            "period": scn.SIMCONNECT_PERIOD_SIM_FRAME,
            "multi": False,
        }
        sc._on_aircraft_title_update("VL3 Asobo")
        sc._on_aircraft_title_update("VL3 Asobo")
        sc._on_aircraft_title_update("C172")
        self.assertEqual(titles, ["VL3 Asobo", "C172"])

    def test_on_dispatch_zombie_hook(self):
        sc = _client()
        called = []
        sc.on_dispatch_zombie = lambda: called.append(True)
        sc._fire_dispatch_zombie_hook()
        self.assertEqual(len(called), 1)


if __name__ == "__main__":
    unittest.main()
