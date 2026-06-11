"""Write queue: submit_set/trigger drained by dispatch thread."""
import ctypes
import threading
import time
import unittest

import simconnect_native as scn
from simconnect_native.registry import VarSlot
from simconnect_native.write_queue import WriteFuture, _WriteOp


class _QueueFakeDll:
    def __init__(self) -> None:
        self.set_threads: list = []
        self.transmit_threads: list = []
        self.maps = 0
        self.transmits = 0
        self.sets = 0
        self._dispatch_block = threading.Event()

    def SimConnect_CallDispatch(self, _h, _cb, _ctx):
        return 0

    def SimConnect_AddToDataDefinition(self, *_a):
        return 0

    def SimConnect_ClearDataDefinition(self, *_a):
        return 0

    def SimConnect_SetDataOnSimObject(self, *_a):
        self.sets += 1
        self.set_threads.append(threading.current_thread().name)
        return 0

    def SimConnect_MapClientEventToSimEvent(self, *_a):
        self.maps += 1
        return 0

    def SimConnect_TransmitClientEvent(self, *_a):
        self.transmits += 1
        self.transmit_threads.append(threading.current_thread().name)
        return 0

    def SimConnect_Close(self, *_a):
        return 0


def _client(dll: _QueueFakeDll | None = None) -> scn.SimConnect:
    sc = scn.SimConnect()
    sc._DispatchProc = ctypes.WINFUNCTYPE(
        None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
    )
    sc._dll = dll or _QueueFakeDll()
    sc._hSimConnect = scn.HANDLE(1)
    sc._open_received = True
    sc.set_dispatch_cb(lambda *_: None)
    return sc


class WriteQueueTests(unittest.TestCase):
    def test_submit_set_drained_on_dispatch_thread(self):
        dll = _QueueFakeDll()
        sc = _client(dll)
        sc.start_background_dispatch()
        time.sleep(0.02)

        fut = sc.submit_set("AMBIENT TEMPERATURE", 18, "Celsius")
        self.assertTrue(fut.wait(2.0))
        self.assertIsNone(fut.error)
        self.assertEqual(dll.sets, 1)
        self.assertEqual(dll.set_threads, ["SimConnectDispatch"])

        sc.stop_background_dispatch(timeout=2.0, force=True)

    def test_set_routes_to_queue_when_dispatch_running(self):
        dll = _QueueFakeDll()
        sc = _client(dll)
        sc.start_background_dispatch()
        time.sleep(0.02)

        sc.set("AMBIENT TEMPERATURE", 20, "Celsius", write_timeout=2.0)
        self.assertEqual(dll.sets, 1)
        self.assertEqual(dll.set_threads, ["SimConnectDispatch"])
        sc.stop_background_dispatch(timeout=2.0, force=True)

    def test_trigger_routes_to_queue_when_dispatch_running(self):
        dll = _QueueFakeDll()
        sc = _client(dll)
        sc.start_background_dispatch()
        time.sleep(0.02)

        sc.trigger("AP_MASTER", write_timeout=2.0)
        sc.trigger("AP_MASTER", write_timeout=2.0)
        self.assertEqual(dll.maps, 1)
        self.assertEqual(dll.transmits, 2)
        self.assertEqual(dll.transmit_threads, ["SimConnectDispatch", "SimConnectDispatch"])
        sc.stop_background_dispatch(timeout=2.0, force=True)

    def test_submit_fire_and_forget_then_flush(self):
        dll = _QueueFakeDll()
        sc = _client(dll)
        sc.start_background_dispatch()
        time.sleep(0.02)

        for i in range(5):
            sc.submit_set("AMBIENT TEMPERATURE", 10 + i, "Celsius")
        self.assertTrue(sc.flush_write_queue(timeout=2.0))
        self.assertEqual(dll.sets, 5)
        sc.stop_background_dispatch(timeout=2.0, force=True)

    def test_direct_set_when_dispatch_not_running(self):
        dll = _QueueFakeDll()
        sc = _client(dll)
        sc.set("AMBIENT TEMPERATURE", 15, "Celsius")
        self.assertEqual(dll.sets, 1)
        self.assertNotEqual(dll.set_threads[0], "SimConnectDispatch")

    def test_concurrent_submit_from_multiple_threads(self):
        dll = _QueueFakeDll()
        sc = _client(dll)
        sc.start_background_dispatch()
        time.sleep(0.02)

        errors = []

        def worker(n: int) -> None:
            try:
                sc.submit_set("AMBIENT TEMPERATURE", n, "Celsius").wait(3.0)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)
        self.assertEqual(errors, [])
        self.assertEqual(dll.sets, 8)
        sc.stop_background_dispatch(timeout=2.0, force=True)

    def test_close_cancels_pending_writes(self):
        dll = _QueueFakeDll()
        sc = _client(dll)
        fut = WriteFuture()
        sc._write_queue.put(
            _WriteOp(execute=lambda _s: None, future=fut, label="pending"),
        )
        with sc._write_queue_done:
            sc._write_queue_pending = 1
        sc.close()
        self.assertTrue(fut.done)
        self.assertIsInstance(fut.error, scn.SimConnectError)
        self.assertEqual(sc.write_queue_depth, 0)

    def test_stop_drains_queue_before_exit(self):
        dll = _QueueFakeDll()
        sc = _client(dll)
        sc.start_background_dispatch()
        time.sleep(0.02)
        sc.submit_set("AMBIENT TEMPERATURE", 1, "Celsius")
        sc.stop_background_dispatch(timeout=2.0)
        self.assertEqual(dll.sets, 1)


class WriteQueueSubscribeConcurrentTests(unittest.TestCase):
    def test_set_during_subscribe_dispatch_still_on_pump_thread(self):
        dll = _QueueFakeDll()
        sc = _client(dll)
        sc._subscriptions[1] = {
            "slot": VarSlot(1, b"PLANE ALTITUDE", b"feet", 4, True),
            "callback": lambda _v: None,
            "period": scn.SIMCONNECT_PERIOD_SIM_FRAME,
            "multi": False,
        }
        sc.start_background_dispatch()
        time.sleep(0.02)

        sc.set("AMBIENT TEMPERATURE", 22, "Celsius", write_timeout=2.0)
        self.assertEqual(dll.set_threads, ["SimConnectDispatch"])
        sc.stop_background_dispatch(timeout=2.0, force=True)


if __name__ == "__main__":
    unittest.main()
