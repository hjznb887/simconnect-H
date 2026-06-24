"""SimVar subscription helpers (mixin for SimConnect).

v0.7.0 — per-subscription health tracking, auto-recovery, data validation, throttled restore.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from ctypes import POINTER, cast

from .constants import (
    SIMCONNECT_DATATYPE_FLOAT64_INT,
    SIMCONNECT_DATATYPE_STRINGV_INT,
    SIMCONNECT_PERIOD_NEVER,
    SIMCONNECT_PERIOD_SIM_FRAME,
    SIMCONNECT_PERIOD_SIM_FRAME_INT,
    SIMCONNECT_RECV_ID_SIMOBJECT_DATA,
    SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE,
    SIMCONNECT_SIMOBJECT_TYPE_USER,
    TYPE_REQ_OFFSET,
)
from .errors import check_hresult
from .fields import (
    FieldsMapping,
    ParsedField,
    build_field_layout,
    parse_fields,
    split_numeric_string_fields,
)
from .utils import as_int, as_non_negative_int, unit_for_simconnect_definition
from .parsing import payload_base, read_data, read_data_at
from .registry import VarSlot
from .structures import SIMOBJECT_DATA_HEADER

logger = logging.getLogger(__name__)

TYPE_REPOLL_INTERVAL = 0.2

# 订阅存活监控默认参数
_SUB_HEALTH_MAX_STALE = 15.0          # 单路超过此秒数无回调 = 不健康
_SUB_HEALTH_GC_INTERVAL = 10.0        # 自动恢复 GC 扫描间隔
_SUB_RESTORE_BATCH_SIZE = 10          # 批量重挂每批最大数
_SUB_RESTORE_BATCH_DELAY = 0.005      # 每批间隔秒数
_SUB_VALUE_MAX_PLAUSIBLE = 1e15       # 单路值绝对值超过此值 = 可疑


class SubscriptionMixin:
    """subscribe() / unsubscribe() / subscribe_many() 与 dispatch 路由。"""

    _subscriptions: Dict[int, Dict[str, Any]]
    _composite_subscriptions: Dict[int, Dict[str, Any]]
    _registry: Any
    _lock: Any

    def _ensure_composite_store(self) -> Dict[int, Dict[str, Any]]:
        store = getattr(self, "_composite_subscriptions", None)
        if store is None:
            store = {}
            self._composite_subscriptions = store
        return store

    # ── 单路订阅存活跟踪 ──────────────────────────────────────

    def _sub_health_store(self) -> Dict[int, float]:
        """sub_id → time.monotonic() 最后回调时间（惰性初始化）。"""
        d = getattr(self, "_sub_last_callback", None)
        if d is None:
            d = {}
            self._sub_last_callback = d
        return d

    def _touch_sub_health(self, sub_id: int) -> None:
        self._sub_health_store()[sub_id] = time.monotonic()

    def subscription_healthy(self, sub_id: int, max_stale: float = _SUB_HEALTH_MAX_STALE) -> bool:
        """检查单路订阅是否健康（近期收到过回调）。"""
        store = getattr(self, "_sub_last_callback", None)
        if store is None:
            return True
        last = store.get(sub_id)
        if last is None:
            return True
        return (time.monotonic() - last) <= max_stale

    def unhealthy_subscriptions(self, max_stale: float = _SUB_HEALTH_MAX_STALE) -> List[int]:
        """返回所有不健康的非组合订阅 sub_id 列表。"""
        store = getattr(self, "_sub_last_callback", None)
        if store is None:
            return []
        now = time.monotonic()
        composites = self._ensure_composite_store()
        result: List[int] = []
        for sub_id, last in list(store.items()):
            if sub_id in composites:
                continue
            if sub_id not in self._subscriptions:
                continue
            if now - last > max_stale:
                result.append(sub_id)
        return result

    # ── 单路数据有效性校验（NaN / inf / 极端值） ────────────

    @staticmethod
    def _value_is_plausible(val: float) -> bool:
        """返回 False 表示值不可信（NaN / inf / 超出合理范围）。"""
        if not isinstance(val, (int, float)):
            return True  # 非数值不判断
        if math.isnan(val) or math.isinf(val):
            return False
        if abs(val) > _SUB_VALUE_MAX_PLAUSIBLE:
            return False
        return True

    # ── 单路恢复（不健康的订阅单独重挂） ────────────────────

    def _resubscribe_one(self, sub_id: int) -> bool:
        """取消并重挂单路订阅，返回是否成功。

        对于 composite 订阅，递归恢复所有子路；对于普通订阅，单路重挂。
        """
        composite = self._ensure_composite_store().get(sub_id)
        if composite is not None:
            ok = True
            for child_id in composite.get("children", []):
                if not self._resubscribe_one(child_id):
                    ok = False
            return ok

        with self._lock:
            info = self._subscriptions.get(sub_id)
            if info is None:
                return False
            # 先彻底取消
            if self.is_open:
                try:
                    self.request_data_on_simobject(
                        sub_id, sub_id, object_id=0, period=SIMCONNECT_PERIOD_NEVER,
                    )
                except Exception:
                    pass
                try:
                    self.clear_data_definition(sub_id)
                except Exception:
                    pass
            info.pop("type_requested", None)
            info.pop("type_req_id", None)
            info.pop("type_repoll_at", None)

        # 再重新注册
        try:
            if info.get("multi"):
                self._prepare_definition(sub_id)
                slot: VarSlot = info["slot"]
                for _key, name, unit, dtype in info["fields"]:
                    check_hresult(
                        self.add_to_data_definition(
                            sub_id,
                            name.encode(),
                            unit_for_simconnect_definition(unit, dtype),
                            dtype,
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
                    f"resubscribe_many sub_id={sub_id}",
                )
                info["type_requested"] = False
                self._request_type_for_subscription(sub_id, info)
            else:
                self._apply_subscription(sub_id, info)
            logger.info("订阅 %d 已恢复", sub_id)
            return True
        except Exception as e:
            logger.warning("恢复订阅 %d 失败: %s", sub_id, e)
            return False

    def _auto_recover_subscriptions(self) -> int:
        """GC 扫描一次，恢复所有不健康订阅。返回恢复数。"""
        now = time.monotonic()
        last = getattr(self, "_sub_last_gc_sweep", 0.0)
        if now - last < _SUB_HEALTH_GC_INTERVAL:
            return 0
        self._sub_last_gc_sweep = now

        unhealthy = self.unhealthy_subscriptions()
        if not unhealthy:
            return 0

        logger.info("自动恢复 %d 路不健康订阅", len(unhealthy))
        recovered = 0
        for sub_id in unhealthy:
            if self._resubscribe_one(sub_id):
                self._touch_sub_health(sub_id)
                recovered += 1
        return recovered

    # ── 批量订阅（入口） ──────────────────────────────────────

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
        self._touch_sub_health(sub_id)
        return sub_id

    def subscribe_string(
        self,
        var_name: str,
        callback: Callable[[str], None],
        period: int = SIMCONNECT_PERIOD_SIM_FRAME_INT,
        *,
        immediate_first: bool = False,
    ) -> int:
        """订阅字符串 SimVar（TITLE / ATC TYPE 等）。

        immediate_first=True 时在后台线程 get_string 一次，避免应用层轮询首帧。
        """
        sub_id = self.subscribe(
            var_name, "", callback, period=period, datatype=SIMCONNECT_DATATYPE_STRINGV_INT,
        )
        if immediate_first and self._ready_for_data_requests():
            self._bootstrap_string_subscription(var_name, callback)
        return sub_id

    def subscribe_many(
        self,
        fields: FieldsMapping,
        callback: Callable[[Dict[str, Any]], None],
        period: int = SIMCONNECT_PERIOD_SIM_FRAME_INT,
    ) -> int:
        """一次订阅多个 SimVar，回调收到 {key: value} 字典。

        数值字段批量打包；字符串字段（TITLE 等）自动并行订阅，合并为同一 dict 回调。
        """
        period = as_non_negative_int("period", as_int(period))
        parsed = parse_fields(fields)
        numeric, string_fields = split_numeric_string_fields(parsed)

        if not string_fields:
            return self._subscribe_many_numeric(numeric, callback, period)

        composite_id = self._registry.alloc_subscription_id()
        state: Dict[str, Any] = {}
        state_lock = threading.Lock()
        child_ids: List[int] = []

        def merge_emit(update: Dict[str, Any]) -> None:
            with state_lock:
                state.update(update)
                snapshot = dict(state)
            callback(snapshot)

        if numeric:
            child_ids.append(
                self._subscribe_many_numeric(
                    numeric,
                    merge_emit,
                    period,
                )
            )

        for key, name, _unit, _dtype in string_fields:
            def on_string(value: str, field_key: str = key) -> None:
                merge_emit({field_key: value})

            child_ids.append(
                self.subscribe_string(name, on_string, period=period)
            )

        with self._lock:
            self._ensure_composite_store()[composite_id] = {"children": child_ids}
        return composite_id

    def _subscribe_many_numeric(
        self,
        parsed: List[ParsedField],
        callback: Callable[[Dict[str, Any]], None],
        period: int,
    ) -> int:
        field_layout = build_field_layout(parsed)

        with self._lock:
            sub_id = self._registry.alloc_subscription_id()
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
        self._touch_sub_health(sub_id)
        return sub_id

    # ── 取消订阅 ──────────────────────────────────────────────

    def unsubscribe(self, sub_id: int) -> bool:
        """取消订阅并清除数据定义。"""
        composite = self._ensure_composite_store().pop(sub_id, None)
        if composite is not None:
            for child_id in composite.get("children", []):
                self.unsubscribe(child_id)
            return True

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
        # 清理健康跟踪
        store = getattr(self, "_sub_last_callback", None)
        if store is not None:
            store.pop(sub_id, None)
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

    # ── 订阅请求管理 ──────────────────────────────────────────

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
                    sub_id,
                    name.encode(),
                    unit_for_simconnect_definition(unit, dtype),
                    dtype,
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

    # ── 调度恢复（全量 / 防抖合并 / 节流） ────────────────────

    def _cancel_restore_timer(self) -> None:
        lock = getattr(self, "_restore_timer_lock", None)
        if lock is None:
            return
        with lock:
            timer = getattr(self, "_restore_timer", None)
            if timer is not None:
                timer.cancel()
                self._restore_timer = None

    def _schedule_restore_subscriptions(self, reason: str = "") -> None:
        """合并 OPEN / SimStart / ASSIGNED_OBJECT_ID 触发的恢复，减轻 MSFS 突发负载。"""
        mark = getattr(self, "mark_dataflow_quiet", None)
        if callable(mark):
            mark(8.0)
        debounce = float(getattr(self, "_restore_debounce_s", 2.0))
        lock = getattr(self, "_restore_timer_lock", None)
        if lock is None:
            self._restore_subscriptions()
            return
        with lock:
            timer = getattr(self, "_restore_timer", None)
            if timer is not None:
                timer.cancel()
            self._restore_timer = threading.Timer(
                debounce,
                self._run_scheduled_restore,
                kwargs={"reason": reason},
            )
            self._restore_timer.daemon = True
            self._restore_timer.start()

    def _run_scheduled_restore(self, reason: str = "") -> None:
        lock = getattr(self, "_restore_timer_lock", None)
        if lock is not None:
            with lock:
                self._restore_timer = None
        if not self.is_open:
            return
        logger.debug("合并恢复 %d 路订阅 (reason=%s)", len(self._subscriptions), reason)
        self._restore_subscriptions()

    def _restore_subscriptions(self) -> None:
        """全量恢复全部订阅——分批执行，每批间隔微小延迟避免 MSFS 瞬间高负载。"""
        self._registry.reset_defined_flags()
        with self._lock:
            items = list(self._subscriptions.items())
        batch_size = _SUB_RESTORE_BATCH_SIZE
        total = len(items)
        for idx in range(0, total, batch_size):
            batch = items[idx:idx + batch_size]
            for sub_id, info in batch:
                try:
                    if info.get("multi"):
                        self._apply_subscription_many(sub_id, info)
                    else:
                        self._apply_subscription(sub_id, info)
                except Exception as e:
                    logger.warning("恢复订阅 %d 失败: %s", sub_id, e)
            if idx + batch_size < total:
                time.sleep(_SUB_RESTORE_BATCH_DELAY)

    # ── TYPE 周期性重发 ──────────────────────────────────────

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

    # ── Dispatch 路由（核心数据通道） ────────────────────────

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

        info, matched_req = self._lookup_subscription(req_id)
        if not info:
            return

        try:
            if info.get("multi"):
                base = payload_base(p_data)
                if base is None:
                    logger.warning("subscribe_many 无 payload, req_id=%s", req_id)
                    return
                values: Dict[str, Any] = {}
                for key, dtype, offset in info["field_layout"]:
                    val = read_data_at(base + offset, dtype)
                    if val is None:
                        logger.warning(
                            "subscribe_many 字段 %s (dtype=%s) 解析失败, req_id=%s",
                            key, dtype, req_id,
                        )
                        return
                    # 校验单个字段有效性
                    if not self._value_is_plausible(val):
                        logger.warning(
                            "subscribe_many 字段 %s 值 %.2e 异常 (req_id=%s)",
                            key, val, req_id,
                        )
                        return
                    values[key] = val
                info["callback"](values)
                self._touch_sub_health(matched_req)
                self.touch_subscription_callback()
            else:
                slot = info["slot"]
                val = read_data(p_data, slot.datatype)
                if val is None:
                    logger.warning(
                        "subscribe 解析失败, req_id=%s, dtype=%s",
                        req_id, slot.datatype,
                    )
                    return
                # 校验单路值有效性
                if not self._value_is_plausible(val):
                    logger.warning(
                        "subscribe 值 %.2e 异常 (req_id=%s, var=%s)",
                        val, req_id,
                        getattr(slot, "var_name", b"").decode(errors="replace"),
                    )
                    return
                info["callback"](val)
                self._touch_sub_health(matched_req)
                self.touch_subscription_callback()
        except Exception as e:
            logger.warning("订阅 %s 回调异常: %s", req_id, e)
