"""Var / event slot registry and ID allocation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


def _var_key(var_name: str, unit: str, datatype: int) -> Tuple[str, str, int]:
    return (var_name.strip().upper(), unit.strip(), int(datatype))


def _event_key(event_name: str) -> str:
    return event_name.strip().upper()


@dataclass
class VarSlot:
    define_id: int
    var_name: bytes
    unit: bytes
    datatype: int
    defined: bool = False


class Registry:
    """管理 SimVar 定义槽与客户端事件 ID。"""

    _VAR_ID_START = 1000

    def __init__(self) -> None:
        self._vars: Dict[Tuple[str, str, int], VarSlot] = {}
        self._define_id_to_key: Dict[int, Tuple[str, str, int]] = {}
        self._next_var_id = self._VAR_ID_START
        self._next_sub_id = 1
        self._events: Dict[str, int] = {}
        self._event_names: Dict[int, bytes] = {}
        self._next_event_id = 1
        self._mapped_events: set[int] = set()

    def alloc_subscription_id(self) -> int:
        sub_id = self._next_sub_id
        self._next_sub_id += 1
        return sub_id

    def bind_subscription_var(
        self,
        define_id: int,
        var_name: str,
        unit: str,
        datatype: int = 4,
    ) -> VarSlot:
        key = _var_key(var_name, unit, datatype)
        name_b = var_name.encode()
        unit_b = unit.encode()
        slot = VarSlot(
            define_id=define_id,
            var_name=name_b,
            unit=unit_b,
            datatype=int(datatype),
        )
        self._vars[key] = slot
        self._define_id_to_key[define_id] = key
        if define_id >= self._next_var_id:
            self._next_var_id = define_id + 1
        return slot

    def get_or_create_var(
        self,
        var_name: str,
        unit: str,
        datatype: int = 4,
    ) -> VarSlot:
        key = _var_key(var_name, unit, datatype)
        slot = self._vars.get(key)
        if slot is not None:
            return slot
        define_id = self._next_var_id
        self._next_var_id += 1
        slot = VarSlot(
            define_id=define_id,
            var_name=var_name.encode(),
            unit=unit.encode(),
            datatype=int(datatype),
        )
        self._vars[key] = slot
        self._define_id_to_key[define_id] = key
        return slot

    def get_var_by_define_id(self, define_id: int) -> Optional[VarSlot]:
        key = self._define_id_to_key.get(define_id)
        if key is None:
            return None
        return self._vars.get(key)

    def release_define_id(self, define_id: int) -> None:
        key = self._define_id_to_key.pop(define_id, None)
        if key is not None:
            self._vars.pop(key, None)

    def reset_defined_flags(self) -> None:
        for slot in self._vars.values():
            slot.defined = False
        self._mapped_events.clear()

    def get_event_id(self, event_name: str) -> Tuple[int, bytes]:
        key = _event_key(event_name)
        name_b = event_name.encode()
        if key not in self._events:
            ev_id = self._next_event_id
            self._next_event_id += 1
            self._events[key] = ev_id
            self._event_names[ev_id] = name_b
        return self._events[key], self._event_names[self._events[key]]

    def is_event_mapped(self, event_id: int) -> bool:
        return event_id in self._mapped_events

    def mark_event_mapped(self, event_id: int) -> None:
        self._mapped_events.add(event_id)
