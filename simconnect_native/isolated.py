"""Killable subprocess host for SimConnect.dll.

Host process never calls SimConnect_Open / CallDispatch. Timeout or zombie:
kill the worker; do not join hung native threads.
"""
from __future__ import annotations

import logging
import multiprocessing
import threading
import time
from typing import Any, Callable, Dict, Optional

from .constants import SIMCONNECT_PERIOD_SIM_FRAME_INT
from .errors import SimConnectNativeHungError, SimConnectOpenTimeoutError

logger = logging.getLogger(__name__)

_STOP = {"op": "shutdown"}


def isolated_worker_main(cmd_q: Any, evt_q: Any) -> None:
    """Child entry (must be module-level for Windows spawn)."""
    from .client import SimConnect

    sc = SimConnect(auto_reconnect=False)
    callbacks: Dict[int, str] = {}

    def emit(payload: Dict[str, Any]) -> None:
        try:
            evt_q.put(payload, timeout=1.0)
        except Exception:
            pass

    def on_many(kind: str, sub_id: int):
        def _cb(data: Any) -> None:
            emit({"op": kind, "sub_id": sub_id, "payload": data})
        return _cb

    last_hb = 0.0
    while True:
        now = time.monotonic()
        if now - last_hb >= 0.5:
            last_hb = now
            emit({
                "op": "heartbeat",
                "healthy": bool(sc.is_open) and sc.is_dataflow_healthy(max_stale=5.0),
                "zombie": sc.dispatch_zombie,
                "native_hung": sc.native_hung,
                "open": sc.is_open,
            })
            if sc.dispatch_zombie or sc._native_hung:
                emit({"op": "zombie"})
        try:
            cmd = cmd_q.get(timeout=0.1)
        except Exception:
            continue
        if not cmd:
            continue
        op = cmd.get("op")
        try:
            if op == "shutdown":
                try:
                    sc.close()
                except Exception:
                    pass
                emit({"op": "bye"})
                return
            if op == "connect":
                sc.connect_hard(
                    cmd.get("app_name", "SimConnectApp"),
                    dll_path=cmd.get("dll_path"),
                    timeout=float(cmd.get("timeout", 5.0)),
                    open_timeout=float(cmd.get("open_timeout", 5.0)),
                    start_dispatch=bool(cmd.get("start_dispatch", True)),
                    wait_open=bool(cmd.get("wait_open", True)),
                )
                emit({"op": "ready"})
            elif op == "subscribe_many":
                sub_id = sc.subscribe_many(
                    cmd["fields"],
                    on_many("data", 0),
                    period=cmd.get("period", SIMCONNECT_PERIOD_SIM_FRAME_INT),
                )
                callbacks[sub_id] = "many"
                emit({"op": "subscribed", "sub_id": sub_id})
            elif op == "set":
                sc.set(cmd["var"], cmd["value"], cmd["unit"])
                emit({"op": "ack", "id": cmd.get("id")})
            elif op == "trigger":
                sc.trigger(cmd["event"], cmd.get("data", 0))
                emit({"op": "ack", "id": cmd.get("id")})
            elif op == "health":
                emit({
                    "op": "health",
                    "healthy": sc.is_dataflow_healthy(max_stale=float(cmd.get("max_stale", 2.0))),
                    "zombie": sc.dispatch_zombie,
                    "native_hung": sc.native_hung,
                })
            else:
                emit({"op": "error", "message": f"unknown op {op!r}"})
        except (SimConnectOpenTimeoutError, SimConnectNativeHungError) as exc:
            emit({"op": "hung", "message": str(exc)})
        except Exception as exc:
            emit({"op": "error", "message": str(exc)})


def _hang_forever(_cmd_q: Any, _evt_q: Any) -> None:
    """Test helper: simulates a worker stuck in native Open."""
    time.sleep(3600)


class IsolatedSimConnect:
    """Parent-side proxy. All DLL calls run in a child process that can be killed."""

    def __init__(
        self,
        *,
        heartbeat_timeout: float = 8.0,
        worker_target: Optional[Callable] = None,
    ) -> None:
        self._ctx = multiprocessing.get_context("spawn")
        self._cmd_q: Any = None
        self._evt_q: Any = None
        self._proc: Any = None
        self._heartbeat_timeout = float(heartbeat_timeout)
        self._worker_target = worker_target or isolated_worker_main
        self._last_heartbeat = 0.0
        self._ready = threading.Event()
        self._hung = False
        self._reader_stop = threading.Event()
        self._reader: Optional[threading.Thread] = None
        self._data_cb: Optional[Callable[[Any], None]] = None
        self._lock = threading.Lock()

    @property
    def worker_alive(self) -> bool:
        p = self._proc
        return p is not None and p.is_alive()

    @property
    def native_hung(self) -> bool:
        return self._hung or (self._proc is not None and not self.worker_alive and self._ready.is_set())

    def connect(
        self,
        app_name: str = "SimConnectApp",
        *,
        open_timeout: float = 5.0,
        timeout: float = 5.0,
        **kwargs: Any,
    ) -> IsolatedSimConnect:
        self._start_worker()
        self._send({
            "op": "connect",
            "app_name": app_name,
            "open_timeout": open_timeout,
            "timeout": timeout,
            **kwargs,
        })
        wait = float(open_timeout) + float(timeout) + 1.0
        if not self._ready.wait(timeout=wait):
            self.kill()
            raise SimConnectOpenTimeoutError(
                "IsolatedSimConnect.connect",
                wait,
                "worker did not become ready; killed",
            )
        if self._hung:
            self.kill()
            raise SimConnectNativeHungError("IsolatedSimConnect.connect")
        return self

    def subscribe_many(
        self,
        fields: Dict[str, Any],
        callback: Callable[[Any], None],
        period: int = SIMCONNECT_PERIOD_SIM_FRAME_INT,
    ) -> None:
        self._data_cb = callback
        self._send({"op": "subscribe_many", "fields": fields, "period": period})

    def set(self, var_name: str, value: Any, unit: str) -> None:
        self._send({"op": "set", "var": var_name, "value": value, "unit": unit})

    def trigger(self, event_name: str, data: Any = 0) -> None:
        self._send({"op": "trigger", "event": event_name, "data": data})

    def is_dataflow_healthy(self, max_stale: float = 2.0) -> bool:
        if not self.worker_alive or self._hung:
            return False
        if self._last_heartbeat <= 0:
            return False
        return (time.monotonic() - self._last_heartbeat) <= max(max_stale, self._heartbeat_timeout)

    def shutdown(self, timeout: float = 2.0) -> None:
        if self.worker_alive:
            try:
                self._send(_STOP)
            except Exception:
                pass
            self._proc.join(timeout=timeout)
        if self.worker_alive:
            self.kill()
        self._stop_reader()

    def kill(self) -> None:
        """Terminate the worker. This is the only recovery for a hung DLL."""
        self._hung = True
        proc = self._proc
        if proc is not None and proc.is_alive():
            logger.error("IsolatedSimConnect.kill() — terminating hung SimConnect worker")
            proc.kill()
            proc.join(timeout=2.0)
        self._proc = None
        self._stop_reader()

    def close(self) -> None:
        self.shutdown()

    def __enter__(self) -> IsolatedSimConnect:
        return self

    def __exit__(self, *_a: Any) -> None:
        self.shutdown()

    def _start_worker(self) -> None:
        if self.worker_alive:
            return
        self._cmd_q = self._ctx.Queue()
        self._evt_q = self._ctx.Queue()
        self._ready.clear()
        self._hung = False
        self._reader_stop.clear()
        self._proc = self._ctx.Process(
            target=self._worker_target,
            args=(self._cmd_q, self._evt_q),
            daemon=True,
            name="SimConnectWorker",
        )
        self._proc.start()
        self._reader = threading.Thread(
            target=self._read_loop, daemon=True, name="SimConnectWorkerReader",
        )
        self._reader.start()
        threading.Thread(
            target=self._watchdog, daemon=True, name="SimConnectWorkerWatchdog",
        ).start()

    def _send(self, cmd: Dict[str, Any]) -> None:
        if self._cmd_q is None:
            raise RuntimeError("worker not started")
        self._cmd_q.put(cmd)

    def _read_loop(self) -> None:
        while not self._reader_stop.is_set():
            try:
                evt = self._evt_q.get(timeout=0.2)
            except Exception:
                continue
            if not evt:
                continue
            op = evt.get("op")
            if op == "heartbeat":
                self._last_heartbeat = time.monotonic()
                if evt.get("zombie") or evt.get("native_hung"):
                    self._hung = True
            elif op == "ready":
                self._last_heartbeat = time.monotonic()
                self._ready.set()
            elif op in ("hung", "zombie"):
                self._hung = True
                self._ready.set()
            elif op == "data" and self._data_cb:
                try:
                    self._data_cb(evt.get("payload"))
                except Exception as exc:
                    logger.warning("IsolatedSimConnect data callback: %s", exc)
            elif op == "error":
                logger.warning("worker error: %s", evt.get("message"))
            elif op == "bye":
                break

    def _watchdog(self) -> None:
        while self.worker_alive and not self._reader_stop.is_set():
            time.sleep(0.5)
            if not self._ready.is_set():
                continue
            if self._last_heartbeat <= 0:
                continue
            if (time.monotonic() - self._last_heartbeat) > self._heartbeat_timeout:
                logger.error("IsolatedSimConnect heartbeat lost — killing worker")
                self.kill()
                return

    def _stop_reader(self) -> None:
        self._reader_stop.set()
