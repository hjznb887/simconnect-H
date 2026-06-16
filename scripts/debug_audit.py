"""Runtime audit for v0.6.0 — writes NDJSON to debug-256491.log"""
from __future__ import annotations

import ctypes
import json
import sys
import threading
import time
from pathlib import Path

LOG_PATH = Path(__file__).resolve().parents[1] / "debug-256491.log"
SESSION = "256491"


def _log(hypothesis_id: str, location: str, message: str, data: dict | None = None) -> None:
    # #region agent log
    payload = {
        "sessionId": SESSION,
        "hypothesisId": hypothesis_id,
        "location": location,
        "message": message,
        "data": data or {},
        "timestamp": int(time.time() * 1000),
        "runId": "audit",
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    # #endregion


def test_collision_double_dispatch() -> None:
    """Hypothesis A: same req_id hits both pending_get and subscriptions."""
    import simconnect_native as scn
    from simconnect_native.constants import TYPE_REQ_OFFSET
    from simconnect_native.registry import VarSlot

    sc = scn.SimConnect()
    sc._DispatchProc = ctypes.WINFUNCTYPE(
        None, scn.POINTER(scn.SIMCONNECT_RECV), scn.DWORD, ctypes.c_void_p,
    )
    sub_hits: list = []
    sc._subscriptions[7] = {
        "slot": VarSlot(7, b"PLANE ALTITUDE", b"feet", 4, True),
        "callback": sub_hits.append,
        "period": scn.SIMCONNECT_PERIOD_SECOND,
        "multi": False,
    }
    evt = threading.Event()
    sc._pending_get[7] = {
        "event": evt,
        "value": None,
        "multi": True,
        "field_layout": [("alt", 4, 0)],
    }
    sc._refresh_dispatch_wrapper()

    size = scn.SIMOBJECT_DATA_PAYLOAD_OFFSET + 8
    buf = ctypes.create_string_buffer(size)
    header = ctypes.cast(buf, ctypes.POINTER(scn.SIMOBJECT_DATA_HEADER)).contents
    header.dwSize = size
    header.dwVersion = 1
    header.dwID = scn.SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE
    type_req = 7 + TYPE_REQ_OFFSET
    header.dwRequestID = type_req
    header.dwDefineCount = 1
    ctypes.memmove(
        ctypes.addressof(buf) + scn.SIMOBJECT_DATA_PAYLOAD_OFFSET,
        ctypes.byref(ctypes.c_double(12345.0)),
        8,
    )
    pkt = ctypes.cast(buf, ctypes.POINTER(scn.SIMCONNECT_RECV))

    sc._dispatch_sync_responses(pkt)
    sc._dispatch_subscriptions(pkt)

    _log(
        "A",
        "debug_audit:test_collision",
        "forced id=7 collision",
        {
            "sub_hits": sub_hits,
            "get_value": sc._pending_get[7].get("value"),
            "event_set": evt.is_set(),
            "dual_dispatch": bool(sub_hits) and evt.is_set(),
        },
    )


def test_simstart_event_id() -> None:
    """Hypothesis B: user SimStart uses 90100 but MSFS sends 90001."""
    import simconnect_native as scn
    from simconnect_native.constants import SIMCONNECT_CLIENT_EVENT_SIMSTART

    sc = scn.SimConnect()
    sc._dll = type("D", (), {"SimConnect_SubscribeToSystemEvent": lambda *a: 0})()
    sc._hSimConnect = scn.HANDLE(1)
    received: list = []

    user_id = sc.subscribe_system_event("SimStart", lambda n, d: received.append((n, d)))
    _log(
        "B",
        "debug_audit:simstart_ids",
        "SimStart id mismatch",
        {
            "internal_simstart_id": SIMCONNECT_CLIENT_EVENT_SIMSTART,
            "user_subscribed_id": user_id,
            "ids_match": user_id == SIMCONNECT_CLIENT_EVENT_SIMSTART,
        },
    )


def test_doctor_exit_code() -> None:
    """Hypothesis C: cmd_doctor ignores diagnose exit code."""
    import runpy
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "examples" / "diagnose_read.py"
    # diagnose_read without MSFS likely returns non-zero; doctor wrapper returns 0
    from simconnect_native.cli import cmd_doctor
    import argparse

    rc_doctor = cmd_doctor(argparse.Namespace())
    _log(
        "C",
        "debug_audit:doctor",
        "cmd_doctor return code",
        {"cmd_doctor_rc": rc_doctor, "note": "run without MSFS — doctor always 0"},
    )


def test_get_many_id_allocator() -> None:
    """Hypothesis A (post-fix): get_many uses 20000+ ids."""
    import simconnect_native as scn

    sc = scn.SimConnect()
    ids = []
    for _ in range(3):
        ids.append(sc.subscribe("PLANE ALTITUDE", "feet", lambda v: None))
    get_id = sc._registry.alloc_get_many_id()
    _log(
        "A",
        "debug_audit:allocator_post_fix",
        "get_many id disjoint",
        {
            "active_sub_ids": ids,
            "get_many_id": get_id,
            "overlaps_active": get_id in ids,
            "get_id_in_dedicated_range": get_id >= 20000,
        },
    )


def test_simstart_post_fix() -> None:
    """Hypothesis B (post-fix): SimStart uses 90001."""
    import simconnect_native as scn
    from simconnect_native.constants import SIMCONNECT_CLIENT_EVENT_SIMSTART

    sc = scn.SimConnect()
    sc._dll = type("D", (), {"SimConnect_SubscribeToSystemEvent": lambda *a: 0})()
    sc._hSimConnect = scn.HANDLE(1)
    user_id = sc.subscribe_system_event("SimStart", lambda n, d: None)
    _log(
        "B",
        "debug_audit:simstart_post_fix",
        "SimStart id fixed",
        {
            "user_subscribed_id": user_id,
            "ids_match": user_id == SIMCONNECT_CLIENT_EVENT_SIMSTART,
        },
    )


if __name__ == "__main__":
    LOG_PATH.unlink(missing_ok=True)
    test_collision_double_dispatch()
    test_simstart_event_id()
    test_simstart_post_fix()
    try:
        test_doctor_exit_code()
    except Exception as exc:
        _log("C", "debug_audit:doctor", "doctor raised", {"error": str(exc)})
    test_get_many_id_allocator()
    print(f"Audit complete — see {LOG_PATH}")
