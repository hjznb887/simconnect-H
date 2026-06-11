"""SimConnect event helpers."""
from __future__ import annotations

from typing import Union

from .constants import (
    SIMCONNECT_EVENT_FLAG_GROUPID_IS_PRIORITY,
    SIMCONNECT_GROUP_PRIORITY_HIGHEST,
)


class EventsMixin:
    """trigger() 事件触发。"""

    _registry: object

    def trigger(
        self,
        event_name: str,
        data: Union[int, float] = 0,
        object_id: int = 0,
        group_priority: int = SIMCONNECT_GROUP_PRIORITY_HIGHEST,
        flags: int = SIMCONNECT_EVENT_FLAG_GROUPID_IS_PRIORITY,
        *,
        write_timeout: float = 5.0,
    ) -> None:
        """按名称触发 SimConnect 事件（后台 dispatch 在跑时走写入队列）。"""
        if not self.is_open:
            raise RuntimeError("SimConnect 未连接，请先调用 open()")

        if self._should_use_write_queue() and not self._is_dispatch_thread():
            self._submit_trigger_and_wait(
                event_name,
                data,
                object_id=object_id,
                group_priority=group_priority,
                flags=flags,
                timeout=write_timeout,
            )
            return

        self._trigger_event_direct(
            event_name,
            data,
            object_id=object_id,
            group_priority=group_priority,
            flags=flags,
        )
