"""SimConnect client — connection, dispatch, and low-level API."""
from __future__ import annotations

import ctypes
import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterable, Iterator, Optional, Tuple

from ctypes import (
    POINTER,
    byref,
    c_char_p,
    c_double,
    c_float,
    c_void_p,
    cast,
)
from ctypes.wintypes import DWORD, HANDLE

from .constants import (
    HRESULT_NAMES,
    SIMCONNECT_CLIENT_EVENT_SIMSTART,
    SIMCONNECT_DATATYPE_FLOAT64_INT,
    SIMCONNECT_DATA_REQUEST_FLAG_DEFAULT,
    SIMCONNECT_EVENT_FLAG_GROUPID_IS_PRIORITY,
    SIMCONNECT_GROUP_PRIORITY_HIGHEST,
    SIMCONNECT_OBJECT_ID_USER,
    SIMCONNECT_PERIOD_SIM_FRAME_INT,
    SIMCONNECT_RECV_ID_ASSIGNED_OBJECT_ID,
    SIMCONNECT_RECV_ID_EVENT,
    SIMCONNECT_RECV_ID_OPEN,
    SIMCONNECT_RECV_ID_QUIT,
    SIMCONNECT_UNUSED,
)
from .dll import find_simconnect_dll, is_untrusted_simconnect_dll
from .parsing import parse_exception, read_data, read_double
from .events import EventsMixin
from .registry import Registry
from .structures import SIMCONNECT_RECV
from .write_queue import WriteQueueMixin
from .sync_io import SyncIOMixin
from .lifecycle import LifecycleMixin
from .weather import WeatherMixin
from .subscribe import SubscriptionMixin
from .system_events import SystemEventsMixin
from .utils import (
    _WinDLL,
    as_c_ulong,
    as_dword,
    is_bare_dll_name,
)

logger = logging.getLogger(__name__)


class SimConnect(
    WriteQueueMixin,
    SyncIOMixin,
    EventsMixin,
    SubscriptionMixin,
    SystemEventsMixin,
    WeatherMixin,
    LifecycleMixin,
):
    """SimConnect 原生封装 — 直接通过 ctypes WinDLL 调用 SimConnect.dll。"""

    def __init__(self, auto_reconnect: bool = True):
        self._dll = None
        self._hSimConnect = None
        self._dispatch_cb = None
        self._user_dispatch_cb = None
        self._DispatchProc = None
        self._app_name = b"SimConnectApp"
        self._dispatch_thread = None
        self._dispatch_running = False
        self._dispatch_stop_event = threading.Event()
        self._lock = threading.Lock()
        self._io_lock = threading.RLock()
        self._dispatch_abandoned = False
        self._last_subscription_callback_at: float = 0.0
        self._auto_reconnect = auto_reconnect
        self._reconnect_delay = 1.0
        self._config_index = 0
        self._registry = Registry()
        self._pending_get: Dict[int, Dict] = {}
        self._get_lock = threading.Lock()
        self._subscriptions: Dict[int, Dict] = {}
        self._user_object_id: int = 0
        self._open_received = False
        self._simstart_subscribed = False
        self._restore_debounce_s = 2.0
        self._restore_timer: Optional[threading.Timer] = None
        self._restore_timer_lock = threading.Lock()
        self._dataflow_quiet_until: float = 0.0
        self._restart_dispatch_cooldown_s = 30.0
        self._last_restart_dispatch_monotonic: float = 0.0
        self.on_connect: Optional[Callable] = None
        self.on_disconnect: Optional[Callable] = None
        self._init_write_queue()
        self._init_lifecycle_hooks()
        self._init_system_events()

    @classmethod
    @contextmanager
    def session(
        cls,
        app_name: str = "SimConnectApp",
        *,
        auto_reconnect: bool = True,
        **connect_kwargs: Any,
    ) -> Iterator[SimConnect]:
        """一键连接上下文：``with SimConnect.session("MyApp") as sc:``"""
        sc = cls(auto_reconnect=auto_reconnect)
        try:
            sc.connect(app_name, **connect_kwargs)
            yield sc
        finally:
            sc.close()

    @property
    def handle(self) -> Optional[HANDLE]:
        return self._hSimConnect

    @property
    def dll(self) -> Optional[Any]:
        return self._dll

    @property
    def is_open(self) -> bool:
        return (
            self._hSimConnect is not None
            and self._hSimConnect.value is not None
            and self._hSimConnect.value != 0
        )

    @property
    def dispatch_thread_alive(self) -> bool:
        t = self._dispatch_thread
        return t is not None and t.is_alive()

    @property
    def dispatch_zombie(self) -> bool:
        """后台 flag 已停但线程仍卡在 CallDispatch 时 True。"""
        return self.dispatch_thread_alive and not self._dispatch_running

    @property
    def last_subscription_callback_monotonic(self) -> float:
        return self._last_subscription_callback_at

    def is_dataflow_healthy(self, max_stale: float = 2.0) -> bool:
        """dispatch 在跑且（有订阅时）近期收到订阅回调。"""
        if not self._dispatch_running or not self.dispatch_thread_alive:
            return False
        if time.monotonic() < self._dataflow_quiet_until:
            return True
        if not self._subscriptions:
            return True
        last = self._last_subscription_callback_at
        if last <= 0.0:
            return False
        return (time.monotonic() - last) <= float(max_stale)

    def mark_dataflow_quiet(self, seconds: float = 8.0) -> None:
        """换机/新航班后短暂静默窗口，避免误判断流。"""
        until = time.monotonic() + float(seconds)
        if until > self._dataflow_quiet_until:
            self._dataflow_quiet_until = until

    def touch_subscription_callback(self) -> None:
        """订阅回调成功时更新（供 SubscriptionMixin 调用）。"""
        self._last_subscription_callback_at = time.monotonic()

    def __repr__(self) -> str:
        status = "已连接" if self.is_open else "未连接"
        dll_status = "已加载" if self._dll else "未加载"
        return f"<SimConnect {status}, DLL {dll_status}>"

    def __enter__(self) -> SimConnect:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def load_dll(self, dll_path: Optional[str] = None) -> None:
        path = os.fspath(dll_path or find_simconnect_dll())
        logger.info("加载 SimConnect.dll: %s", path)
        if is_untrusted_simconnect_dll(path):
            logger.warning(
                "检测到 SimConnect.dll 来自便携/下载目录: %s\n"
                "建议删除该文件，改用 MSFS SDK 中的 SimConnect.dll，"
                "或设置环境变量 SIMCONNECT_DLL 指向 SDK 路径",
                path,
            )

        if _WinDLL is None:
            raise OSError(
                "SimConnect.dll 只能通过 Windows 的 ctypes.WinDLL 加载；"
                "当前平台不支持直接连接 MSFS"
            )

        if not is_bare_dll_name(path) and not os.path.isfile(path):
            raise FileNotFoundError(
                f"SimConnect.dll 未找到: {path}\n"
                "请确保已安装 MSFS 或从 SDK 获取 SimConnect.dll"
            )

        try:
            self._dll = _WinDLL(path)
        except OSError as e:
            raise OSError(
                f"加载 SimConnect.dll 失败: {e}\n"
                "请检查:\n"
                "  1. DLL 是 64 位版本（Python 也是 64 位）\n"
                "  2. 已安装 Microsoft Visual C++ Redistributable\n"
                "  3. DLL 未被其他进程独占锁定"
            ) from e

        logger.debug("SimConnect.dll 加载成功")
        self._setup_argtypes()
        self._refresh_dispatch_wrapper()

    def _setup_argtypes(self) -> None:
        d = self._dll

        d.SimConnect_Open.restype = ctypes.c_long
        d.SimConnect_Open.argtypes = [
            POINTER(HANDLE),
            c_char_p,
            c_void_p,
            DWORD,
            HANDLE,
            DWORD,
        ]

        d.SimConnect_Close.restype = ctypes.c_long
        d.SimConnect_Close.argtypes = [HANDLE]

        self._DispatchProc = ctypes.WINFUNCTYPE(
            None, POINTER(SIMCONNECT_RECV), DWORD, c_void_p,
        )
        d.SimConnect_CallDispatch.restype = ctypes.c_long
        d.SimConnect_CallDispatch.argtypes = [
            HANDLE,
            self._DispatchProc,
            c_void_p,
        ]

        d.SimConnect_AddToDataDefinition.restype = ctypes.c_long
        d.SimConnect_AddToDataDefinition.argtypes = [
            HANDLE,
            DWORD,
            c_char_p,
            c_char_p,
            ctypes.c_ulong,
            c_float,
            DWORD,
        ]

        d.SimConnect_RequestDataOnSimObjectType.restype = ctypes.c_long
        d.SimConnect_RequestDataOnSimObjectType.argtypes = [
            HANDLE,
            DWORD,
            DWORD,
            DWORD,
            ctypes.c_ulong,
        ]

        d.SimConnect_RequestDataOnSimObject.restype = ctypes.c_long
        d.SimConnect_RequestDataOnSimObject.argtypes = [
            HANDLE,
            DWORD,
            DWORD,
            DWORD,
            ctypes.c_ulong,
            DWORD,
            DWORD,
            DWORD,
            DWORD,
        ]

        d.SimConnect_SetDataOnSimObject.restype = ctypes.c_long
        d.SimConnect_SetDataOnSimObject.argtypes = [
            HANDLE,
            DWORD,
            ctypes.c_ulong,
            DWORD,
            DWORD,
            DWORD,
            c_void_p,
        ]

        d.SimConnect_MapClientEventToSimEvent.restype = ctypes.c_long
        d.SimConnect_MapClientEventToSimEvent.argtypes = [HANDLE, DWORD, c_char_p]

        d.SimConnect_TransmitClientEvent.restype = ctypes.c_long
        d.SimConnect_TransmitClientEvent.argtypes = [
            HANDLE,
            ctypes.c_ulong,
            DWORD,
            DWORD,
            DWORD,
            DWORD,
        ]

        d.SimConnect_SubscribeToSystemEvent.restype = ctypes.c_long
        d.SimConnect_SubscribeToSystemEvent.argtypes = [HANDLE, DWORD, c_char_p]

        d.SimConnect_GetLastSentPacketID.restype = ctypes.c_long
        d.SimConnect_GetLastSentPacketID.argtypes = [HANDLE, POINTER(DWORD)]

        d.SimConnect_ClearDataDefinition.restype = ctypes.c_long
        d.SimConnect_ClearDataDefinition.argtypes = [HANDLE, DWORD]

        d.SimConnect_WeatherSetModeCustom.restype = ctypes.c_long
        d.SimConnect_WeatherSetModeCustom.argtypes = [HANDLE]

        d.SimConnect_WeatherSetObservation.restype = ctypes.c_long
        d.SimConnect_WeatherSetObservation.argtypes = [HANDLE, DWORD, c_char_p]

    def open(
        self,
        app_name: Any = b"SimConnectApp",
        window_handle: Any = None,
        fifo_size: int = 0,
        window_event_handle: Any = None,
        config_index: int = 0,
    ) -> HANDLE:
        if not self._dll:
            self.load_dll()
        if isinstance(app_name, str):
            app_name = app_name.encode("utf-8")

        h_sim = HANDLE(0)
        with self._io_lock:
            err = self._dll.SimConnect_Open(
                ctypes.byref(h_sim),
                app_name,
                window_handle,
                as_dword(fifo_size),
                window_event_handle,
                as_dword(config_index),
            )
        if err != 0:
            name = HRESULT_NAMES.get(err, "")
            msg = f"SimConnect_Open 失败: HRESULT=0x{err:08x}"
            if name:
                msg += f" ({name})"
            raise ConnectionError(msg)
        if not h_sim or h_sim.value is None or h_sim.value == 0:
            raise ConnectionError("SimConnect_Open 返回空句柄 — MSFS 可能未运行")
        self._hSimConnect = h_sim
        self._app_name = app_name
        self._config_index = int(config_index)
        self._reconnect_delay = 1.0
        self._open_received = False
        self._refresh_dispatch_wrapper()
        logger.info(
            "SimConnect 已连接 (app=%s, config_index=%d)",
            app_name,
            self._config_index,
        )
        self._ensure_simstart_subscribed()
        if self.on_connect:
            try:
                self.on_connect()
            except Exception as e:
                logger.debug("on_connect 回调异常: %s", e)
        return h_sim

    def connect(
        self,
        app_name: Any = b"SimConnectApp",
        *,
        dll_path: Optional[str] = None,
        timeout: float = 5.0,
        config_indices: Iterable[int] = range(8),
        start_dispatch: bool = True,
        wait_open: bool = True,
    ) -> SimConnect:
        """一键连接 MSFS（开发验证用：游戏已开时直接连，扫 config_index 0–7）。"""
        if not self._dll:
            self.load_dll(dll_path)

        deadline = time.monotonic() + float(timeout)
        last_err: Optional[Exception] = None

        for idx in config_indices:
            try:
                if self.is_open:
                    self.close()
                self.open(app_name, config_index=idx)
            except ConnectionError as exc:
                last_err = exc
                logger.debug("config_index=%d 连接失败: %s", idx, exc)
                continue

            if wait_open:
                self._pump_until_open(deadline)
            ready = self._open_received if wait_open else self.is_open
            if ready:
                if start_dispatch and not self._dispatch_running:
                    self.start_background_dispatch()
                logger.info(
                    "connect() 成功 (config_index=%d, open=%s)",
                    idx,
                    self._open_received,
                )
                return self

            logger.debug(
                "config_index=%d 已 Open 但未收到 OPEN 消息，尝试下一个",
                idx,
            )
            self.close()

        hint = f": {last_err}" if last_err else ""
        raise ConnectionError(
            f"未能连接 MSFS（已尝试 config_index={list(config_indices)}）{hint}"
        )

    def _pump_until_open(self, deadline: float) -> None:
        """在 deadline 前 pump dispatch，直到收到 OPEN。"""
        while time.monotonic() < deadline and not self._open_received:
            if self._dispatch_cb:
                self.dispatch()
            time.sleep(0.005)

    def close(self) -> None:
        self._cancel_restore_timer()
        self.stop_background_dispatch(timeout=5.0, force=True)
        self._cancel_write_queue()
        with self._lock:
            h_sim = self._hSimConnect
            defined_ids = self._registry.defined_define_ids()
            self._hSimConnect = None
            self._open_received = False
            self._simstart_subscribed = False
            self._user_object_id = 0
        if self._dll and h_sim:
            for define_id in defined_ids:
                try:
                    err = self._dll.SimConnect_ClearDataDefinition(
                        h_sim, as_dword(define_id),
                    )
                    if err != 0:
                        logger.debug(
                            "ClearDataDefinition(%s)=0x%08x on close",
                            define_id,
                            err,
                        )
                except Exception as e:
                    logger.debug(
                        "ClearDataDefinition(%s) on close: %s", define_id, e,
                    )
            try:
                self._dll.SimConnect_Close(h_sim)
                logger.info("SimConnect 已断开")
            except Exception as e:
                logger.debug("SimConnect_Close 异常: %s", e)
            self._registry.reset_defined_flags()

    def _parse_assigned_object_id(self, p_data: Any) -> Optional[int]:
        """SIMCONNECT_RECV_ASSIGNED_OBJECT_ID.dwObjectID 在头部后第 2 个 DWORD。"""
        try:
            base = cast(p_data, c_void_p).value
            return int(cast(base + 16, POINTER(DWORD)).contents.value)
        except Exception:
            return None

    def _sim_object_id(self) -> int:
        """用户飞机 objectID；未分配前使用 SIMCONNECT_OBJECT_ID_USER。"""
        if self._user_object_id:
            return self._user_object_id
        return int(SIMCONNECT_OBJECT_ID_USER.value)

    def _ready_for_data_requests(self) -> bool:
        return self.is_open and self._open_received

    def _ensure_simstart_subscribed(self) -> None:
        if self._simstart_subscribed or not self.is_open:
            return
        err = self.subscribe_to_system_event(
            SIMCONNECT_CLIENT_EVENT_SIMSTART,
            b"SimStart",
        )
        if err == 0:
            self._simstart_subscribed = True
            logger.debug("已订阅系统事件 SimStart")
        else:
            logger.debug("SubscribeToSystemEvent(SimStart)=0x%08x", err)

    def call_dispatch(self, callback: Callable) -> None:
        if not self._dll:
            return
        with self._lock:
            self._dispatch_cb = self._DispatchProc(callback)
            cb = self._dispatch_cb
            h_sim = self._hSimConnect
        if not h_sim or not h_sim.value:
            return
        with self._io_lock:
            self._dll.SimConnect_CallDispatch(h_sim, cb, None)

    def dispatch(self) -> None:
        if not self._dll:
            return
        with self._lock:
            cb = self._dispatch_cb
            h_sim = self._hSimConnect
        if not cb or not h_sim or not h_sim.value:
            return
        with self._io_lock:
            self._dll.SimConnect_CallDispatch(h_sim, cb, None)

    def set_dispatch_cb(self, callback: Optional[Callable]) -> None:
        with self._lock:
            self._user_dispatch_cb = callback
            self._refresh_dispatch_wrapper()

    def _refresh_dispatch_wrapper(self) -> None:
        if not self._DispatchProc:
            return

        def combined(p_data, cb_data, p_context):
            try:
                dw_id = p_data.contents.dwID
                if dw_id == SIMCONNECT_RECV_ID_OPEN:
                    self._open_received = True
                    self._registry.reset_defined_flags()
                    self._cancel_restore_timer()
                    self.mark_dataflow_quiet(8.0)
                    self._restore_subscriptions()
                    self._fire_sim_start_hooks("OPEN")
                elif dw_id == SIMCONNECT_RECV_ID_QUIT:
                    logger.info("收到 QUIT — 模拟器已断开")
                    with self._lock:
                        self._hSimConnect = None
                        self._open_received = False
                        self._user_object_id = 0
                        self._simstart_subscribed = False
                elif dw_id == SIMCONNECT_RECV_ID_ASSIGNED_OBJECT_ID:
                    obj_id = self._parse_assigned_object_id(p_data)
                    if obj_id is not None:
                        self._user_object_id = obj_id
                        logger.debug("用户飞机 objectID=%s", obj_id)
                    self._schedule_restore_subscriptions("ASSIGNED_OBJECT_ID")
                    self._fire_sim_start_hooks("ASSIGNED_OBJECT_ID")
                elif dw_id == SIMCONNECT_RECV_ID_EVENT:
                    from .structures import SIMCONNECT_RECV_EVENT

                    evt = cast(p_data, POINTER(SIMCONNECT_RECV_EVENT)).contents
                    if int(evt.uEventID) == SIMCONNECT_CLIENT_EVENT_SIMSTART:
                        logger.info("收到 SimStart — 合并恢复数据请求")
                        self._schedule_restore_subscriptions("SimStart")
                        self._fire_sim_start_hooks("SimStart")
                        self._dispatch_system_events(p_data)
                    else:
                        self._dispatch_system_events(p_data)
            except Exception:
                pass
            self._dispatch_sync_responses(p_data)
            self._dispatch_subscriptions(p_data)
            self._repoll_type_subscriptions()
            if self._user_dispatch_cb:
                try:
                    self._user_dispatch_cb(p_data, cb_data, p_context)
                except Exception as e:
                    logger.warning("用户 dispatch 回调异常: %s", e)

        self._dispatch_cb = self._DispatchProc(combined)

    def ensure_background_dispatch(self) -> None:
        """若后台 dispatch 未运行则启动（幂等）。"""
        if not self._dispatch_running:
            self.start_background_dispatch()

    @contextmanager
    def with_paused_dispatch(
        self,
        *,
        restart: bool = True,
        stop_timeout: float = 5.0,
        force: bool = False,
    ) -> Iterator[SimConnect]:
        """暂停后台 pump，供同步写入 / 天气 API 等场景；finally 可选恢复。"""
        was_running = self._dispatch_running
        if was_running:
            self.stop_background_dispatch(timeout=stop_timeout, force=force)
        try:
            yield self
        finally:
            if restart and was_running:
                self.restart_dispatch(force=force)

    def restart_dispatch(self, *, force: bool = False) -> None:
        """重启后台 dispatch 并恢复订阅。"""
        now = time.monotonic()
        if (
            not force
            and self._last_restart_dispatch_monotonic > 0.0
            and (now - self._last_restart_dispatch_monotonic)
            < self._restart_dispatch_cooldown_s
        ):
            logger.debug(
                "restart_dispatch 跳过（%.0fs 冷却中）",
                self._restart_dispatch_cooldown_s,
            )
            return
        self._last_restart_dispatch_monotonic = now
        self.restart_background_dispatch(force=force)
        if self.is_open and self._open_received:
            self._restore_subscriptions()

    def restart_background_dispatch(self, *, force: bool = False) -> None:
        stopped = self.stop_background_dispatch(timeout=5.0, force=force)
        if not stopped and not force:
            logger.warning(
                "restart_background_dispatch: stop 未在超时内完成，"
                "请使用 force=True 或 with_paused_dispatch(force=True)"
            )
            return
        self.start_background_dispatch()

    def start_background_dispatch(self, callback: Optional[Callable] = None) -> None:
        if callback is not None:
            self.set_dispatch_cb(callback)
        if not self._dispatch_cb:
            self._refresh_dispatch_wrapper()
        if not self._dispatch_cb and not self._subscriptions:
            raise RuntimeError(
                "请先通过 set_dispatch_cb 设置回调，或使用 subscribe()/get() 注册活动"
            )
        if self._dispatch_running:
            logger.debug("后台 dispatch 已在运行")
            return

        if self.dispatch_thread_alive and not self._dispatch_running:
            self._dispatch_abandoned = True
            logger.warning(
                "dispatch zombie：旧 pump 线程仍存活，启动新 dispatch 线程"
            )

        self._dispatch_stop_event.clear()
        self._dispatch_running = True
        self._dispatch_thread = threading.Thread(
            target=self._dispatch_loop,
            daemon=True,
            name="SimConnectDispatch",
        )
        self._dispatch_thread.start()
        logger.debug("后台 dispatch 线程已启动")

    def stop_background_dispatch(
        self,
        timeout: float = 5.0,
        *,
        force: bool = False,
    ) -> bool:
        """停止后台 dispatch。返回 True 表示线程已退出；False 表示 zombie。"""
        self._dispatch_running = False
        self._dispatch_stop_event.set()
        thread = self._dispatch_thread
        if thread and thread.is_alive():
            thread.join(timeout=float(timeout))
            if thread.is_alive():
                logger.warning(
                    "dispatch zombie（线程 %.1fs 内未退出，可能卡在 CallDispatch）",
                    timeout,
                )
                if force:
                    self._dispatch_abandoned = True
                self._fire_dispatch_zombie_hook()
                return False
        self._dispatch_thread = None
        self._dispatch_abandoned = False
        logger.debug("后台 dispatch 已停止")
        return True

    def _dispatch_loop(self) -> None:
        while self._dispatch_running or self._write_queue_pending > 0:
            if self.is_open and self._dispatch_running:
                try:
                    self.dispatch()
                except Exception as e:
                    logger.warning("dispatch 异常: %s，1 秒后重试", e)
                    if self._dispatch_stop_event.wait(timeout=1.0):
                        break
                    continue
            if self._write_queue_pending > 0:
                self._drain_write_queue()
            if not self._dispatch_running and self._write_queue_pending == 0:
                break
            if not self.is_open and self._dispatch_running and self._auto_reconnect:
                if self._dispatch_stop_event.wait(timeout=self._reconnect_delay):
                    break
                try:
                    self.open(self._app_name, config_index=self._config_index)
                    if not self._open_received:
                        self._pump_until_open(time.monotonic() + 5.0)
                    logger.info("自动重连成功")
                except Exception as e:
                    self._reconnect_delay = min(self._reconnect_delay * 1.5, 30.0)
                    logger.debug("重连尝试失败: %s", e)
            else:
                self._dispatch_stop_event.wait(timeout=0.001)

        if self.on_disconnect and not self.is_open:
            try:
                self.on_disconnect()
            except Exception:
                pass

    def add_to_data_definition(
        self,
        define_id: int,
        simvar_name: bytes,
        unit: Optional[bytes],
        datatype: int = SIMCONNECT_DATATYPE_FLOAT64_INT,
        epsilon: float = 0.0,
        datasize: int = int(SIMCONNECT_UNUSED.value),
    ) -> int:
        with self._io_lock:
            return self._dll.SimConnect_AddToDataDefinition(
                self._hSimConnect,
                as_dword(define_id),
                simvar_name,
                unit,
                as_c_ulong(datatype),
                c_float(epsilon),
                as_dword(datasize),
            )

    def clear_data_definition(self, define_id: int) -> int:
        with self._io_lock:
            return self._dll.SimConnect_ClearDataDefinition(
                self._hSimConnect, as_dword(define_id),
            )

    def request_data_on_simobject_type(
        self,
        request_id: int,
        define_id: int,
        object_id: int = 0,
        simobject_type: int = 0,
    ) -> int:
        with self._io_lock:
            return self._dll.SimConnect_RequestDataOnSimObjectType(
                self._hSimConnect,
                as_dword(request_id),
                as_dword(define_id),
                as_dword(object_id),
                as_c_ulong(simobject_type),
            )

    def request_data_on_simobject(
        self,
        request_id: int,
        define_id: int,
        object_id: int = 0,
        period: int = SIMCONNECT_PERIOD_SIM_FRAME_INT,
        flags: int = SIMCONNECT_DATA_REQUEST_FLAG_DEFAULT,
        origin: int = 0,
        interval: int = 0,
        limit: int = 0,
    ) -> int:
        with self._io_lock:
            return self._dll.SimConnect_RequestDataOnSimObject(
                self._hSimConnect,
                as_dword(request_id),
                as_dword(define_id),
                as_dword(object_id),
                as_c_ulong(period),
                as_dword(flags),
                as_dword(origin),
                as_dword(interval),
                as_dword(limit),
            )

    def add_and_request(
        self,
        request_id: int,
        define_id: int,
        simvar_name: bytes,
        unit: bytes,
        datatype: int = SIMCONNECT_DATATYPE_FLOAT64_INT,
        period: int = SIMCONNECT_PERIOD_SIM_FRAME_INT,
    ) -> int:
        err = self.clear_data_definition(define_id)
        if err != 0:
            logger.debug("ClearDataDefinition(%s) = 0x%08x", define_id, err)
        err = self.add_to_data_definition(define_id, simvar_name, unit, datatype)
        if err != 0:
            return err
        return self.request_data_on_simobject(
            request_id, define_id, object_id=0, period=period,
        )

    def set_data_on_simobject(
        self,
        define_id: int,
        object_id: int = 0,
        flags: int = 0,
        array_count: int = 1,
        unit_size: int = 8,
        data_ptr: Optional[c_void_p] = None,
    ) -> Optional[int]:
        if data_ptr is None:
            return None
        with self._io_lock:
            return self._dll.SimConnect_SetDataOnSimObject(
                self._hSimConnect,
                as_dword(define_id),
                as_c_ulong(object_id),
                as_dword(flags),
                as_dword(array_count),
                as_dword(unit_size),
                data_ptr,
            )

    def write_double(self, define_id: int, value: float) -> Optional[int]:
        data = c_double(float(value))
        return self.set_data_on_simobject(
            define_id, data_ptr=cast(byref(data), c_void_p),
        )

    @staticmethod
    def event_data_float(value: float) -> int:
        return ctypes.cast(byref(c_float(float(value))), POINTER(DWORD)).contents.value

    def map_client_event_to_sim_event(self, event_id: int, event_name: bytes) -> int:
        with self._io_lock:
            return self._dll.SimConnect_MapClientEventToSimEvent(
                self._hSimConnect, as_dword(event_id), event_name,
            )

    def transmit_client_event(
        self,
        object_id: int = 0,
        event_id: int = 0,
        data: int = 0,
        group_priority: int = SIMCONNECT_GROUP_PRIORITY_HIGHEST,
        flags: int = SIMCONNECT_EVENT_FLAG_GROUPID_IS_PRIORITY,
    ) -> int:
        with self._io_lock:
            return self._dll.SimConnect_TransmitClientEvent(
                self._hSimConnect,
                as_c_ulong(object_id),
                as_dword(event_id),
                as_dword(data),
                as_dword(group_priority),
                as_dword(flags),
            )

    def subscribe_to_system_event(self, event_id: int, event_name: bytes) -> int:
        with self._io_lock:
            return self._dll.SimConnect_SubscribeToSystemEvent(
                self._hSimConnect, as_dword(event_id), event_name,
            )

    def get_last_sent_packet_id(self) -> int:
        pid = DWORD(0)
        with self._io_lock:
            self._dll.SimConnect_GetLastSentPacketID(
                self._hSimConnect, ctypes.byref(pid),
            )
        return pid.value

    def read_double(self, p_data: Any) -> Tuple[Optional[int], Optional[float]]:
        return read_double(p_data)

    @staticmethod
    def read_data(p_data: Any, datatype: int = SIMCONNECT_DATATYPE_FLOAT64_INT) -> Any:
        return read_data(p_data, datatype)

    @staticmethod
    def parse_exception(
        p_data: Any,
    ) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        return parse_exception(p_data)
