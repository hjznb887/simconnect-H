"""SimVar subscription helpers (mixin for SimConnect)."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from ctypes import POINTER, cast

from .constants import (
    SIMCONNECT_DATATYPE_FLOAT64_INT,
    SIMCONNECT_PERIOD_NEVER,
    SIMCONNECT_PERIOD_SIM_FRAME,
    SIMCONNECT_PERIOD_SIM_FRAME_INT,
    SIMCONNECT_RECV_ID_SIMOBJECT_DATA,
    SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE,
    SIMCONNECT_SIMOBJECT_TYPE_USER,
    TYPE_REQ_OFFSET,
)
from .errors import check_hresult
from .utils import as_int, as_non_negative_int
from .parsing import DATATYPE_SIZES, payload_base, read_data, read_data_at
from .registry import VarSlot
from .structures import SIMOBJECT_DATA_HEADER

logger = logging.getLogger(__name__)

TYPE_REPOLL_INTERVAL = 0.2

FieldSpec = Union[Tuple[str, str], Tuple[str, str, int]]


class SubscriptionMixin:
    """subscribe() / unsubscribe() / subscribe_many() 与 dispatch 路由。"""

    _subscriptions: Dict[int, Dict[str, Any]]
    _registry: Any
    _lock: Any

    def subscribe(
        self,
        var_name: str,
        unit: str,
        callback: Callable[[Any], None],
        period: int = SIMCONNECT_PERIOD_SIM_FRAME_INT,
        datatype: int = SIMCONNECT_DATATYPE_FLOAT64_INT,
    ) -> int:
        """注册 SimVar 订阅（自动管理定义 + 请求 + dispatch 分发）。"""
        period = as_non_negative_int("period", as_int(period))
        datatype = as_non_negative_int("datatype", as_int(datatype))
        with self._lock:
            sub_id = self._registry.alloc_subscription_id()
            slot = self._registry.bind_subscription_var(
                sub_id, var_name, unit, datatype,
            )
            info = {
                "slot": slot,
                "callback": callback,
                "period": period,
                "multi": False,
            }
            self._subscriptions[sub_id] = info
            self._refresh_dispatch_wrapper()
            if self._ready_for_data_requests():
                self._apply_subscription(sub_id, info)
        return sub_id

    def subscribe_many(
        self,
        fields: Dict[str, FieldSpec],
        callback: Callable[[Dict[str, Any]], None],
        period: int = SIMCONNECT_PERIOD_SIM_FRAME_INT,
    ) -> int:
        """一次订阅多个 SimVar，回调收到 {key: value} 字典。"""
        period = as_non_negative_int("period", as_int(period))
        parsed: List[Tuple[str, str, str, int]] = []
        for key, spec in fields.items():
            if len(spec) == 2:
                name, unit = spec
                dtype = SIMCONNECT_DATATYPE_FLOAT64_INT
            else:
                name, unit, dtype = spec
                dtype = as_non_negative_int(f"fields[{key!r}] datatype", int(dtype))
            parsed.append((key, name, unit, dtype))

        with self._lock:
            sub_id = self._registry.alloc_subscription_id()
            field_layout: List[Tuple[str, int, int]] = []
            offset = 0
            for key, name, unit, dtype in parsed:
                size = DATATYPE_SIZES.get(dtype)
                if size is None:
                    raise ValueError(
                        f"subscribe_many 暂不支持 datatype={dtype}（字段 {key!r}）"
                    )
                field_layout.append((key, dtype, offset))
                offset += size

            slot = VarSlot(
                define_id=sub_id,
                var_name=b"",
                unit=b"",
                datatype=SIMCONNECT_DATATYPE_FLOAT64_INT,
            )
            info = {
                "slot": slot,
                "callback": callback,
                "period": period,
                "multi": True,
                "fields": parsed,
                "field_layout": field_layout,
            }
            self._subscriptions[sub_id] = info
            self._refresh_dispatch_wrapper()
            if self._ready_for_data_requests():
                self._apply_subscription_many(sub_id, info)
        return sub_id

    def unsubscribe(self, sub_id: int) -> bool:
        """取消订阅并清除数据定义。"""
        with self._lock:
            info = self._subscriptions.pop(sub_id, None)
            if info is None:
                return False
            self._refresh_dispatch_wrapper()

        if self.is_open:
            try:
                self.request_data_on_simobject(
                    sub_id, sub_id, object_id=0, period=SIMCONNECT_PERIOD_NEVER,
                )
            except Exception as e:
                logger.debug("停止订阅 %s 请求失败: %s", sub_id, e)
            try:
                self.clear_data_definition(sub_id)
            except Exception as e:
                logger.debug("清除定义 %s 失败: %s", sub_id, e)
            if info.get("multi") or self._registry.get_var_by_define_id(sub_id):
                self._registry.release_define_id(sub_id)
        return True

    def _prepare_definition(self, define_id: int) -> None:
        """重连/OPEN 后先清旧定义，避免 AddToDataDefinition 叠加重读。"""
        slot = self._registry.get_var_by_define_id(define_id)
        if slot is None or not slot.defined:
            return
        if self.is_open:
            err = self.clear_data_definition(define_id)
            if err != 0:
                logger.debug("ClearDataDefinition(%s)=0x%08x", define_id, err)
        slot.defined = False

    def _request_type_for_subscription(self, sub_id: int, info: dict) -> None:
        if info.get("type_requested"):
            return
        slot = info["slot"]
        if not slot.defined:
            return
        type_req = sub_id + TYPE_REQ_OFFSET
        check_hresult(
            self.request_data_on_simobject_type(
                type_req,
                slot.define_id,
                0,
                SIMCONNECT_SIMOBJECT_TYPE_USER,
            ),
            "RequestDataOnSimObjectType",
            f"sub_id={sub_id}",
        )
        info["type_req_id"] = type_req
        info["type_requested"] = True

    def _request_all_type_subscriptions(self) -> None:
        with self._lock:
            items = list(self._subscriptions.items())
        for sub_id, info in items:
            try:
                self._request_type_for_subscription(sub_id, info)
            except Exception as e:
                logger.debug("TYPE 请求 %s 失败: %s", sub_id, e)

    def _lookup_subscription(self, req_id: int) -> Tuple[Optional[dict], int]:
        with self._lock:
            info = self._subscriptions.get(req_id)
            if info is not None:
                return info, req_id
            if req_id >= TYPE_REQ_OFFSET:
                base_id = req_id - TYPE_REQ_OFFSET
                info = self._subscriptions.get(base_id)
                if info is not None:
                    return info, req_id
        return None, req_id

    def _apply_subscription(self, sub_id: int, info: dict) -> None:
        slot = info["slot"]
        self._prepare_definition(slot.define_id)
        self._ensure_var_defined(slot)
        period = info["period"]
        obj_id = self._sim_object_id()
        check_hresult(
            self.request_data_on_simobject(
                sub_id, slot.define_id, object_id=obj_id, period=period,
            ),
            "RequestDataOnSimObject",
            f"sub_id={sub_id}",
        )
        info["type_requested"] = False
        self._request_type_for_subscription(sub_id, info)

    def _apply_subscription_many(self, sub_id: int, info: dict) -> None:
        self._prepare_definition(sub_id)
        slot: VarSlot = info["slot"]
        for _key, name, unit, dtype in info["fields"]:
            check_hresult(
                self.add_to_data_definition(
                    sub_id, name.encode(), unit.encode(), dtype,
                ),
                "AddToDataDefinition",
                name,
            )
        slot.defined = True
        obj_id = self._sim_object_id()
        check_hresult(
            self.request_data_on_simobject(
                sub_id, sub_id, object_id=obj_id, period=info["period"],
            ),
            "RequestDataOnSimObject",
            f"subscribe_many sub_id={sub_id}",
        )
        info["type_requested"] = False
        self._request_type_for_subscription(sub_id, info)

    def _restore_subscriptions(self) -> None:
        self._registry.reset_defined_flags()
        with self._lock:
            items = list(self._subscriptions.items())
        for sub_id, info in items:
            try:
                if info.get("multi"):
                    self._apply_subscription_many(sub_id, info)
                else:
                    self._apply_subscription(sub_id, info)
            except Exception as e:
                logger.warning("恢复订阅 %d 失败: %s", sub_id, e)

    def _repoll_type_subscriptions(self) -> None:
        """MSFS 上 RequestDataOnSimObjectType 常为单次请求，需周期性重发（同 SimvarWatcher）。"""
        if not self._ready_for_data_requests():
            return
        now = time.monotonic()
        with self._lock:
            items = list(self._subscriptions.items())
        for sub_id, info in items:
            last = float(info.get("type_repoll_at", 0.0))
            if now - last < TYPE_REPOLL_INTERVAL:
                continue
            info["type_repoll_at"] = now
            info["type_requested"] = False
            try:
                self._request_type_for_subscription(sub_id, info)
            except Exception as e:
                logger.debug("TYPE 重发 %s 失败: %s", sub_id, e)

    def _dispatch_subscriptions(self, p_data: Any) -> None:
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

        info, _matched_req = self._lookup_subscription(req_id)
        if not info:
            return

        try:
            if info.get("multi"):
                base = payload_base(p_data)
                if base is None:
                    return
                values: Dict[str, Any] = {}
                for key, dtype, offset in info["field_layout"]:
                    val = read_data_at(base + offset, dtype)
                    if val is None:
                        return
                    values[key] = val
                info["callback"](values)
            else:
                slot = info["slot"]
                val = read_data(p_data, slot.datatype)
                if val is None:
                    return
                info["callback"](val)
        except Exception as e:
            logger.warning("订阅 %s 回调异常: %s", req_id, e)
