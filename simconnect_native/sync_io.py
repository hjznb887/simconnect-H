"""Synchronous get/set SimVar helpers."""
from __future__ import annotations

import ctypes
import threading
import time
from typing import Any, Union

from ctypes import c_void_p, cast

from .constants import (
    SIMCONNECT_DATATYPE_FLOAT64_INT,
    SIMCONNECT_DATATYPE_STRINGV_INT,
    SIMCONNECT_PERIOD_ONCE,
    SIMCONNECT_SIMOBJECT_TYPE_USER,
    TYPE_REQ_OFFSET,
)
from .errors import SimConnectTimeoutError, check_hresult
from .parsing import DATATYPE_SIZES
from .registry import VarSlot
from .utils import as_int, as_non_negative_int, unit_for_simconnect_definition


class SyncIOMixin:
    """get() / set() 同步读写。"""

    _registry: Any
    _pending_get: dict
    _lock: Any

    def get(
        self,
        var_name: str,
        unit: str,
        timeout: float = 0.1,
        datatype: int = SIMCONNECT_DATATYPE_FLOAT64_INT,
        object_id: int = 0,
    ) -> Any:
        """同步读取 SimVar（PERIOD_ONCE，默认 timeout 100ms，无缓存）。"""
        if timeout <= 0:
            raise ValueError(f"timeout must be > 0, got {timeout}")
        datatype = as_non_negative_int("datatype", as_int(datatype))
        if not self.is_open:
            raise RuntimeError("SimConnect 未连接，请先调用 open()")

        with self._get_lock:
            return self._get_locked(
                var_name, unit, timeout, datatype, object_id,
            )

    def _get_locked(
        self,
        var_name: str,
        unit: str,
        timeout: float,
        datatype: int,
        object_id: int,
    ) -> Any:
        deadline_open = time.monotonic() + float(timeout)
        while not self._open_received and time.monotonic() < deadline_open:
            if self._dispatch_cb and not self._dispatch_running:
                self.dispatch()
            time.sleep(0.005)
        if not self._open_received:
            raise SimConnectTimeoutError("get(open)", timeout, "未收到 OPEN 消息")

        slot = self._registry.get_or_create_var(var_name, unit, datatype)
        self._prepare_definition(slot.define_id)
        self._ensure_var_defined(slot)
        req_id = slot.define_id

        event = threading.Event()
        with self._lock:
            self._pending_get[req_id] = {
                "event": event,
                "value": None,
                "datatype": as_int(datatype),
            }
            self._refresh_dispatch_wrapper()

        try:
            check_hresult(
                self.request_data_on_simobject_type(
                    req_id + TYPE_REQ_OFFSET,
                    slot.define_id,
                    0,
                    SIMCONNECT_SIMOBJECT_TYPE_USER,
                ),
                "RequestDataOnSimObjectType",
                f"var={var_name!r}",
            )

            deadline = time.monotonic() + float(timeout)
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                if event.wait(timeout=min(0.01, max(remaining, 0.0))):
                    with self._lock:
                        pending = self._pending_get.get(req_id)
                    if pending and pending["value"] is not None:
                        return pending["value"]
                    break
                if self._dispatch_cb and not self._dispatch_running:
                    self.dispatch()

            raise SimConnectTimeoutError("get", timeout, f"var={var_name!r}")
        finally:
            with self._lock:
                self._pending_get.pop(req_id, None)
                self._refresh_dispatch_wrapper()

    def get_string(
        self,
        var_name: str,
        timeout: float = 1.0,
        object_id: int = 0,
    ) -> str:
        """读取字符串 SimVar（TITLE / ATC TYPE 等，unit=NULL，STRINGV）。"""
        return self.get(
            var_name,
            "",
            timeout=timeout,
            datatype=SIMCONNECT_DATATYPE_STRINGV_INT,
            object_id=object_id,
        )

    def set(
        self,
        var_name: str,
        value: Union[int, float],
        unit: str,
        datatype: int = SIMCONNECT_DATATYPE_FLOAT64_INT,
        object_id: int = 0,
        *,
        write_timeout: float = 5.0,
    ) -> None:
        """写入 SimVar（后台 dispatch 在跑时走写入队列）。"""
        datatype = as_non_negative_int("datatype", as_int(datatype))
        if not self.is_open:
            raise RuntimeError("SimConnect 未连接，请先调用 open()")

        if self._should_use_write_queue() and not self._is_dispatch_thread():
            self._submit_set_and_wait(
                var_name,
                value,
                unit,
                datatype=datatype,
                object_id=object_id,
                timeout=write_timeout,
            )
            return

        buf, unit_size = self._pack_set_value(value, datatype)
        self._set_var_direct(
            var_name, unit, datatype, object_id, buf, unit_size,
        )

    def set_string(
        self,
        var_name: str,
        value: str,
        object_id: int = 0,
        *,
        write_timeout: float = 5.0,
    ) -> None:
        """写入字符串 SimVar（STRINGV 长度前缀 + 数据）。"""
        if not self.is_open:
            raise RuntimeError("SimConnect 未连接，请先调用 open()")

        if self._should_use_write_queue() and not self._is_dispatch_thread():
            self._submit_set_string_and_wait(
                var_name,
                value,
                object_id=object_id,
                timeout=write_timeout,
            )
            return

        buf, unit_size = self._pack_set_string_value(value)
        self._set_var_direct(
            var_name,
            "", SIMCONNECT_DATATYPE_STRINGV_INT, object_id, buf, unit_size,
        )

    def _ensure_var_defined(self, slot: VarSlot) -> None:
        if slot.defined:
            return
        check_hresult(
            self.add_to_data_definition(
                slot.define_id,
                slot.var_name,
                unit_for_simconnect_definition(slot.unit, slot.datatype),
                slot.datatype,
            ),
            "AddToDataDefinition",
            slot.var_name.decode(errors="replace"),
        )
        slot.defined = True

    def _dispatch_sync_responses(self, p_data: Any) -> None:
        from ctypes import POINTER, cast

        from .constants import (
            SIMCONNECT_RECV_ID_SIMOBJECT_DATA,
            SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE,
        )
        from .parsing import read_data
        from .structures import SIMOBJECT_DATA_HEADER

        try:
            dw_id = p_data.contents.dwID
        except Exception:
            return
        if dw_id not in (
            SIMCONNECT_RECV_ID_SIMOBJECT_DATA,
            SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE,
        ):
            return
        try:
            header = cast(p_data, POINTER(SIMOBJECT_DATA_HEADER)).contents
            req_id = int(header.dwRequestID)
        except Exception:
            return

        with self._lock:
            pending = self._pending_get.get(req_id)
            if pending is None and req_id >= TYPE_REQ_OFFSET:
                pending = self._pending_get.get(req_id - TYPE_REQ_OFFSET)
        if not pending:
            return

        val = read_data(p_data, pending["datatype"])
        if val is None:
            return
        pending["value"] = val
        pending["event"].set()
