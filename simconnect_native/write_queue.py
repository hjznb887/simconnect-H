"""Write queue — set/trigger 由 dispatch 线程串行执行。"""
from __future__ import annotations

import logging
import struct
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple, Union

from ctypes import byref, c_double, c_float, c_int32, c_int64, c_void_p, cast, create_string_buffer

from .constants import SIMCONNECT_DATATYPE_FLOAT64_INT, SIMCONNECT_DATATYPE_STRINGV_INT
from .errors import SimConnectError, SimConnectWriteTimeoutError, check_hresult
from .utils import as_int, as_non_negative_int

logger = logging.getLogger(__name__)

WriteExecuteFn = Callable[[Any], None]


@dataclass
class _WriteOp:
    execute: WriteExecuteFn
    future: Optional["WriteFuture"] = None
    label: str = ""
    _buffers: Tuple[Any, ...] = field(default_factory=tuple, repr=False)


class WriteFuture:
    """异步写入完成句柄。"""

    __slots__ = ("_event", "_error", "_result", "_label")

    def __init__(self, label: str = "write queue operation") -> None:
        self._event = threading.Event()
        self._error: Optional[BaseException] = None
        self._result: Any = None
        self._label = label

    @property
    def done(self) -> bool:
        return self._event.is_set()

    @property
    def error(self) -> Optional[BaseException]:
        return self._error

    def wait(self, timeout: Optional[float] = None) -> bool:
        return self._event.wait(timeout)

    def result_or_raise(self, timeout: Optional[float] = None) -> Any:
        if timeout is not None and not self.wait(timeout):
            raise SimConnectWriteTimeoutError(self._label, timeout)
        if not self.done:
            self.wait()
        if self._error is not None:
            raise self._error
        return self._result

    def _set_result(self, value: Any) -> None:
        self._result = value
        self._event.set()

    def _set_error(self, exc: BaseException) -> None:
        self._error = exc
        self._event.set()


class WriteQueueMixin:
    """写入队列 mixin — 供 SimConnect 继承。"""

    _write_queue: deque[_WriteOp]
    _write_queue_pending: int
    _write_queue_done: threading.Condition
    _dispatch_running: bool
    _dispatch_thread: Optional[threading.Thread]
    _registry: Any

    def _init_write_queue(self) -> None:
        self._write_queue = deque()
        self._write_queue_pending = 0
        self._write_queue_done = threading.Condition()

    @property
    def write_queue_depth(self) -> int:
        with self._write_queue_done:
            return self._write_queue_pending

    @property
    def write_queue_enabled(self) -> bool:
        """后台 dispatch 在跑时，set/trigger 默认走队列。"""
        return self._should_use_write_queue()

    def _should_use_write_queue(self) -> bool:
        return bool(self._dispatch_running)

    def _is_dispatch_thread(self) -> bool:
        thread = self._dispatch_thread
        return thread is not None and threading.current_thread() is thread

    def submit(self, execute: WriteExecuteFn, *, label: str = "submit") -> WriteFuture:
        """提交任意写入操作，由 pump 线程执行。"""
        return self._enqueue_write(execute, label=label)

    def submit_set(
        self,
        var_name: str,
        value: Union[int, float],
        unit: str,
        *,
        datatype: int = SIMCONNECT_DATATYPE_FLOAT64_INT,
        object_id: int = 0,
    ) -> WriteFuture:
        """异步入队 SetDataOnSimObject。"""
        datatype = as_non_negative_int("datatype", as_int(datatype))
        buf, unit_size = self._pack_set_value(value, datatype)
        label = f"set({var_name!r})"

        def execute(sc: Any) -> None:
            sc._set_var_direct(
                var_name, unit, datatype, object_id, buf, unit_size,
            )

        return self._enqueue_write(
            execute,
            label=label,
            buffers=(buf,),
        )

    def submit_set_string(
        self,
        var_name: str,
        value: str,
        *,
        object_id: int = 0,
    ) -> WriteFuture:
        """异步入队字符串 SimVar 写入。"""
        buf, unit_size = self._pack_set_string_value(value)
        label = f"set_string({var_name!r})"

        def execute(sc: Any) -> None:
            sc._set_var_direct(
                var_name,
                "",
                SIMCONNECT_DATATYPE_STRINGV_INT,
                object_id,
                buf,
                unit_size,
            )

        return self._enqueue_write(
            execute,
            label=label,
            buffers=(buf,),
        )

    def submit_trigger(
        self,
        event_name: str,
        data: Union[int, float] = 0,
        *,
        object_id: int = 0,
        group_priority: Optional[int] = None,
        flags: Optional[int] = None,
    ) -> WriteFuture:
        """异步入队 TransmitClientEvent（含懒映射）。"""
        label = f"trigger({event_name!r})"

        def execute(sc: Any) -> None:
            sc._trigger_event_direct(
                event_name,
                data,
                object_id=object_id,
                group_priority=group_priority,
                flags=flags,
            )

        return self._enqueue_write(execute, label=label)

    def flush_write_queue(self, timeout: float = 5.0) -> bool:
        """等待队列中已提交写入全部执行完成。"""
        deadline = time.monotonic() + float(timeout)
        with self._write_queue_done:
            while self._write_queue_pending > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._write_queue_done.wait(timeout=min(0.02, remaining))
            return True

    def _enqueue_write(
        self,
        execute: WriteExecuteFn,
        *,
        label: str,
        buffers: Tuple[Any, ...] = (),
        wait: bool = False,
        wait_timeout: float = 5.0,
    ) -> WriteFuture:
        if not self.is_open:
            raise RuntimeError("SimConnect 未连接，请先调用 open()")

        future = WriteFuture(label=label)
        op = _WriteOp(
            execute=execute,
            future=future,
            label=label,
            _buffers=buffers,
        )

        if self._should_use_write_queue() and not self._is_dispatch_thread():
            with self._write_queue_done:
                self._write_queue.append(op)
                self._write_queue_pending += 1
                self._write_queue_done.notify_all()
            if wait:
                future.result_or_raise(wait_timeout)
            return future

        self._execute_write_op(op, from_queue=False)
        if wait:
            future.result_or_raise(0.0)
        return future

    def _execute_write_op(self, op: _WriteOp, *, from_queue: bool = True) -> None:
        try:
            op.execute(self)
        except BaseException as exc:
            logger.debug("写入队列项 %s 失败: %s", op.label, exc)
            if op.future is not None:
                op.future._set_error(exc)
        else:
            if op.future is not None:
                op.future._set_result(None)
        finally:
            if from_queue:
                with self._write_queue_done:
                    if self._write_queue_pending > 0:
                        self._write_queue_pending -= 1
                    if self._write_queue_pending == 0:
                        self._write_queue_done.notify_all()

    def _drain_write_queue(self, max_items: int = 256) -> int:
        """由 dispatch 线程在 CallDispatch 之间调用。"""
        count = 0
        while count < max_items:
            with self._write_queue_done:
                if not self._write_queue:
                    break
                op = self._write_queue.popleft()
            self._execute_write_op(op)
            count += 1
        return count

    def _cancel_write_queue(self, reason: str = "SimConnect 已关闭") -> None:
        """close 时丢弃未执行项并唤醒 waiters。"""
        err = SimConnectError("WriteQueue", 0, reason)
        with self._write_queue_done:
            while self._write_queue:
                op = self._write_queue.popleft()
                if op.future is not None and not op.future.done:
                    op.future._set_error(err)
            self._write_queue_pending = 0
            self._write_queue_done.notify_all()

    @staticmethod
    def _pack_set_value(
        value: Union[int, float],
        datatype: int,
    ) -> Tuple[Any, int]:
        dtype = as_int(datatype)
        if dtype == 4:
            buf = c_double(float(value))
            return buf, 8
        if dtype == 3:
            buf = c_float(float(value))
            return buf, 4
        if dtype == 1:
            buf = c_int32(int(value))
            return buf, 4
        if dtype == 2:
            buf = c_int64(int(value))
            return buf, 8
        raise ValueError(f"set() 暂不支持 datatype={dtype}")

    @staticmethod
    def _pack_set_string_value(value: str) -> Tuple[Any, int]:
        text = value.encode("utf-8")
        payload = struct.pack("<i", len(text) + 1) + text + b"\x00"
        buf = create_string_buffer(payload)
        return buf, len(payload)

    @staticmethod
    def _data_ptr(buf: Any) -> c_void_p:
        if isinstance(buf, (c_double, c_float, c_int32, c_int64)):
            return cast(byref(buf), c_void_p)
        return cast(buf, c_void_p)

    def _set_var_direct(
        self,
        var_name: str,
        unit: str,
        datatype: int,
        object_id: int,
        buf: Any,
        unit_size: int,
    ) -> None:
        slot = self._registry.get_or_create_var(var_name, unit, datatype)
        self._prepare_definition(slot.define_id)
        self._ensure_var_defined(slot)
        check_hresult(
            self.set_data_on_simobject(
                slot.define_id,
                object_id=object_id or self._sim_object_id(),
                unit_size=unit_size,
                data_ptr=self._data_ptr(buf),
            ),
            "SetDataOnSimObject",
            f"var={var_name!r}",
        )

    def _trigger_event_direct(
        self,
        event_name: str,
        data: Union[int, float],
        *,
        object_id: int = 0,
        group_priority: Optional[int] = None,
        flags: Optional[int] = None,
    ) -> None:
        from .constants import (
            SIMCONNECT_EVENT_FLAG_GROUPID_IS_PRIORITY,
            SIMCONNECT_GROUP_PRIORITY_HIGHEST,
        )

        if group_priority is None:
            group_priority = SIMCONNECT_GROUP_PRIORITY_HIGHEST
        if flags is None:
            flags = SIMCONNECT_EVENT_FLAG_GROUPID_IS_PRIORITY

        event_id, name_b = self._registry.get_event_id(event_name)
        if not self._registry.is_event_mapped(event_id):
            check_hresult(
                self.map_client_event_to_sim_event(event_id, name_b),
                "MapClientEventToSimEvent",
                event_name,
            )
            self._registry.mark_event_mapped(event_id)

        if isinstance(data, float):
            data = self.event_data_float(data)

        check_hresult(
            self.transmit_client_event(
                object_id=object_id,
                event_id=event_id,
                data=int(data),
                group_priority=group_priority,
                flags=flags,
            ),
            "TransmitClientEvent",
            event_name,
        )

    def _submit_set_and_wait(
        self,
        var_name: str,
        value: Union[int, float],
        unit: str,
        *,
        datatype: int,
        object_id: int,
        timeout: float,
    ) -> None:
        self.submit_set(
            var_name,
            value,
            unit,
            datatype=datatype,
            object_id=object_id,
        ).result_or_raise(timeout)

    def _submit_set_string_and_wait(
        self,
        var_name: str,
        value: str,
        *,
        object_id: int,
        timeout: float,
    ) -> None:
        self.submit_set_string(
            var_name, value, object_id=object_id,
        ).result_or_raise(timeout)

    def _submit_trigger_and_wait(
        self,
        event_name: str,
        data: Union[int, float],
        *,
        object_id: int,
        group_priority: int,
        flags: int,
        timeout: float,
    ) -> None:
        self.submit_trigger(
            event_name,
            data,
            object_id=object_id,
            group_priority=group_priority,
            flags=flags,
        ).result_or_raise(timeout)
