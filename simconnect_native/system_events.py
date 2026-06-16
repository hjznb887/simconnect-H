"""MSFS system event subscriptions (Pause, SimStop, etc.)."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from ctypes import POINTER, cast

from .constants import SIMCONNECT_CLIENT_EVENT_SIMSTART, SIMCONNECT_RECV_ID_EVENT
from .errors import check_hresult
from .structures import SIMCONNECT_RECV_EVENT

logger = logging.getLogger(__name__)

_SYSTEM_EVENT_ID_START = 90100

MSFS_SYSTEM_EVENTS = frozenset({
    "SimStart",
    "SimStop",
    "Pause",
    "Unpause",
    "Crash",
    "Crashed",
    "AircraftLoaded",
    "FlightLoaded",
    "ObjectAdd",
    "ObjectRemove",
    "Frame",
    "WeatherChanged",
})


class SystemEventsMixin:
    """subscribe_system_event() — 监听模拟器系统事件。"""

    _system_event_handlers: Dict[int, Dict[str, Any]]
    _next_system_event_id: int

    def _init_system_events(self) -> None:
        self._system_event_handlers = {}
        self._next_system_event_id = _SYSTEM_EVENT_ID_START

    def subscribe_system_event(
        self,
        event_name: str,
        callback: Callable[[str, int], None],
    ) -> int:
        """订阅 MSFS 系统事件；回调 ``callback(event_name, dwData)``。"""
        name = event_name.strip()
        if not name:
            raise ValueError("event_name 不能为空")
        if not self.is_open:
            raise RuntimeError("SimConnect 未连接，请先调用 open() / connect()")
        if name == "SimStart":
            event_id = SIMCONNECT_CLIENT_EVENT_SIMSTART
            if event_id not in self._system_event_handlers:
                err = self.subscribe_to_system_event(event_id, b"SimStart")
                check_hresult(err, "SubscribeToSystemEvent", "event=SimStart")
                self._simstart_subscribed = True
        else:
            event_id = self._alloc_system_event_id()
            err = self.subscribe_to_system_event(event_id, name.encode())
            check_hresult(err, "SubscribeToSystemEvent", f"event={name!r}")
        self._system_event_handlers[event_id] = {
            "name": name,
            "callback": callback,
        }
        logger.debug("已订阅系统事件 %s (id=%d)", name, event_id)
        return event_id

    def unsubscribe_system_event(self, event_id: int) -> bool:
        """移除本地系统事件回调（MSFS 侧订阅无法撤销）。"""
        return self._system_event_handlers.pop(int(event_id), None) is not None

    def _alloc_system_event_id(self) -> int:
        event_id = self._next_system_event_id
        self._next_system_event_id += 1
        return event_id

    def _dispatch_system_events(self, p_data: Any) -> None:
        try:
            if p_data.contents.dwID != SIMCONNECT_RECV_ID_EVENT:
                return
        except Exception:
            return
        try:
            evt = cast(p_data, POINTER(SIMCONNECT_RECV_EVENT)).contents
            event_id = int(evt.uEventID)
            info = self._system_event_handlers.get(event_id)
            if info is None:
                return
            info["callback"](info["name"], int(evt.dwData))
        except Exception as exc:
            logger.warning("系统事件回调异常: %s", exc)
