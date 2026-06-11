"""SimConnect event helpers."""
from __future__ import annotations

from typing import Union

from .constants import (
    SIMCONNECT_EVENT_FLAG_GROUPID_IS_PRIORITY,
    SIMCONNECT_GROUP_PRIORITY_HIGHEST,
)
from .errors import check_hresult


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
    ) -> None:
        """按名称触发 SimConnect 事件（懒映射 MapClientEventToSimEvent）。"""
        if not self.is_open:
            raise RuntimeError("SimConnect 未连接，请先调用 open()")

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
