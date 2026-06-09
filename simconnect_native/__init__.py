# simconnect_native.py
"""原生 ctypes SimConnect 库 — 零外部依赖，可直接加载 SimConnect.dll 与 MSFS 通讯。

用法:
    from libs.simconnect_native import SimConnect, SIMCONNECT_SIMOBJECT_TYPE_USER

    sc = SimConnect()
    sc.open("MyApp")
    # 注册数据定义
    sc.add_to_data_definition(1, b"PLANE ALTITUDE", b"Feet", 0)  # 0=FLOAT64
    # 请求数据
    sc.request_data_on_simobject_type(1, 1, 0, SIMCONNECT_SIMOBJECT_TYPE_USER)
    # dispatch 回调
    def on_dispatch(pData, cbData, pContext):
        dwID = pData.contents.dwID
        ...
    sc.call_dispatch(on_dispatch)
    # 写入
    sc.set_data_on_simobject(2, SIMCONNECT_SIMOBJECT_TYPE_USER, 0, 0, 8, data_ptr)
    # 事件
    sc.map_client_event_to_sim_event(100, b"KEY_TOGGLE")
    sc.transmit_client_event(0, 100, 0, 0x19000000, 16)
    sc.close()

不依赖 PySimConnect（AGPL）的任何代码。
"""
import ctypes
import os
import logging
from ctypes import (c_ulong, c_float, c_char_p, c_double, c_void_p,
                    cast, POINTER, sizeof as c_sizeof, Structure, WinDLL)
from ctypes.wintypes import HANDLE, DWORD, HRESULT

__all__ = [
    # 常量
    "SIMCONNECT_UNUSED", "SIMCONNECT_OBJECT_ID_USER",
    "SIMCONNECT_DATATYPE_FLOAT64", "SIMCONNECT_DATATYPE_FLOAT32",
    "SIMCONNECT_DATATYPE_INT32", "SIMCONNECT_DATATYPE_INT16",
    "SIMCONNECT_DATATYPE_INT8", "SIMCONNECT_DATATYPE_STRINGV",
    "SIMCONNECT_SIMOBJECT_TYPE_USER", "SIMCONNECT_SIMOBJECT_TYPE_ALL",
    "SIMCONNECT_SIMOBJECT_TYPE_AIRCRAFT",
    "SIMCONNECT_PERIOD_NEVER", "SIMCONNECT_PERIOD_ONCE",
    "SIMCONNECT_PERIOD_VISUAL_FRAME", "SIMCONNECT_PERIOD_SIM_FRAME",
    "SIMCONNECT_PERIOD_SECOND",
    "SIMCONNECT_RECV_ID_NULL", "SIMCONNECT_RECV_ID_EXCEPTION",
    "SIMCONNECT_RECV_ID_OPEN", "SIMCONNECT_RECV_ID_QUIT",
    "SIMCONNECT_RECV_ID_EVENT", "SIMCONNECT_RECV_ID_SIMOBJECT_DATA",
    "SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE",
    "EXCEPTION_NAMES",
    # 结构体
    "SIMCONNECT_RECV", "FULL_SIMOBJECT_DATA", "EXCEPTION_MSG",
    # 事件
    "MSFS_EVENTS",
    # 函数
    "find_simconnect_dll",
    # 类
    "SimConnect",
]

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════

SIMCONNECT_UNUSED = DWORD(0xFFFFFFFF)
SIMCONNECT_OBJECT_ID_USER = DWORD(0)

# SIMCONNECT_DATATYPE
SIMCONNECT_DATATYPE_FLOAT64   = c_ulong(0)
SIMCONNECT_DATATYPE_FLOAT32   = c_ulong(1)
SIMCONNECT_DATATYPE_INT32     = c_ulong(2)
SIMCONNECT_DATATYPE_INT16     = c_ulong(3)
SIMCONNECT_DATATYPE_INT8      = c_ulong(4)
SIMCONNECT_DATATYPE_STRINGV   = c_ulong(5)

# SIMCONNECT_SIMOBJECT_TYPE
SIMCONNECT_SIMOBJECT_TYPE_USER    = c_ulong(0)
SIMCONNECT_SIMOBJECT_TYPE_ALL     = c_ulong(1)
SIMCONNECT_SIMOBJECT_TYPE_AIRCRAFT = c_ulong(2)

# SIMCONNECT_PERIOD
SIMCONNECT_PERIOD_NEVER          = c_ulong(0)
SIMCONNECT_PERIOD_ONCE           = c_ulong(1)
SIMCONNECT_PERIOD_VISUAL_FRAME   = c_ulong(2)
SIMCONNECT_PERIOD_SIM_FRAME      = c_ulong(3)
SIMCONNECT_PERIOD_SECOND         = c_ulong(4)

# SIMCONNECT_RECV_ID
SIMCONNECT_RECV_ID_NULL                      = 0
SIMCONNECT_RECV_ID_EXCEPTION                 = 1
SIMCONNECT_RECV_ID_OPEN                      = 2
SIMCONNECT_RECV_ID_QUIT                      = 3
SIMCONNECT_RECV_ID_EVENT                     = 4
SIMCONNECT_RECV_ID_EVENT_OBJECT_ADDREMOVE     = 5
SIMCONNECT_RECV_ID_EVENT_FILENAME             = 6
SIMCONNECT_RECV_ID_EVENT_FRAME                = 7
SIMCONNECT_RECV_ID_SIMOBJECT_DATA             = 14
SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE      = 15
SIMCONNECT_RECV_ID_WEATHER_OBSERVATION        = 16
SIMCONNECT_RECV_ID_CLIENT_DATA                = 19
SIMCONNECT_RECV_ID_EVENT_WEATHER_MODE         = 20
SIMCONNECT_RECV_ID_EVENT_MULTIPLAYER_SERVER_STARTED = 27
SIMCONNECT_RECV_ID_EVENT_MULTIPLAYER_CLIENT_STARTED = 28
SIMCONNECT_RECV_ID_EVENT_MULTIPLAYER_SESSION_ENDED   = 29
SIMCONNECT_RECV_ID_EVENT_RACE_END             = 30
SIMCONNECT_RECV_ID_EVENT_RACE_LAP             = 31
SIMCONNECT_RECV_ID_SYSTEM_STATE               = 33

# SIMCONNECT_EXCEPTION
EXCEPTION_NAMES = {
    0: "NONE", 1: "ERROR", 2: "SIZE_MISMATCH", 3: "UNRECOGNIZED_ID",
    4: "UNOPENED", 5: "VERSION_MISMATCH", 6: "TOO_MANY_GROUPS",
    7: "NAME_UNRECOGNIZED", 8: "TOO_MANY_EVENT_NAMES",
}

# ═══════════════════════════════════════════════════
# 消息结构体
# ═══════════════════════════════════════════════════

class SIMCONNECT_RECV(Structure):
    """SimConnect 消息头部（所有消息的前 16 字节）"""
    _fields_ = [
        ("dwID", DWORD),
        ("dwSize", DWORD),
        ("dwVersion", DWORD),
        ("dwSeqNumber", DWORD),
    ]


class FULL_SIMOBJECT_DATA(Structure):
    """完整的数据消息（含头部），用于 SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE"""
    _fields_ = [
        ("dwID", DWORD), ("dwSize", DWORD), ("dwVersion", DWORD), ("dwSeqNumber", DWORD),
        ("dwRequestID", DWORD), ("dwObjectID", DWORD), ("dwDefineID", DWORD),
        ("dwFlags", DWORD), ("dwentrynumber", DWORD), ("dwoutof", DWORD),
        ("dwDefineCount", DWORD), ("dwData", c_ulong * 8192),
    ]


class EXCEPTION_MSG(Structure):
    """异常消息（含头部）"""
    _fields_ = [
        ("dwID", DWORD), ("dwSize", DWORD), ("dwVersion", DWORD), ("dwSeqNumber", DWORD),
        ("dwException", DWORD), ("UNKNOWN_SENDID", DWORD),
        ("UNKNOWN_INDEX", DWORD), ("dwSendID", DWORD), ("dwIndex", DWORD),
    ]


# ═══════════════════════════════════════════════════
# 事件名称查询表
# ═══════════════════════════════════════════════════

MSFS_EVENTS = {
    # 引擎
    "THROTTLE_FULL": False, "THROTTLE_INCR": False, "THROTTLE_DECR": False,
    "THROTTLE_CUT": False, "MIXTURE_INCR": False, "MIXTURE_DECR": False,
    "PROP_PITCH_INCR": False, "PROP_PITCH_DECR": False,
    # 飞行控制
    "AP_MASTER": False, "AP_PANEL_ALTITUDE_HOLD": False, "AP_PANEL_HEADING_HOLD": False,
    "AP_PANEL_SPEED_HOLD": False, "AP_PANEL_ATTITUDE_HOLD": False,
    # 灯光
    "LANDING_LIGHTS_TOGGLE": False, "STROBES_TOGGLE": False,
    "BEACONS_TOGGLE": False, "NAV_LIGHTS_TOGGLE": False, "TAXI_LIGHTS_TOGGLE": False,
    "PANEL_LIGHTS_TOGGLE": False,
    # 系统
    "GEAR_TOGGLE": False, "PARKING_BRAKES": False,
    "SIM_RESET": False, "SITUATION_RESET": False, "REPAIR_AND_REFUEL": False,
    "TOGGLE_ENGINE": False, "TOGGLE_MASTER_IGNITION": False,
    "TOGGLE_ALTERNATOR": False, "TOGGLE_AVIONICS_MASTER": False,
    # 视图
    "VIEW_RESET": False, "EYEPOINT_RESET": False, "PAN_RESET": False,
    # 襟翼
    "FLAPS_INCR": False, "FLAPS_DECR": False, "FLAPS_UP": False, "FLAPS_DOWN": False,
    # 配平
    "ELEV_TRIM_UP": False, "ELEV_TRIM_DN": False,
    "AILERON_TRIM_LEFT": False, "AILERON_TRIM_RIGHT": False,
    "RUDDER_TRIM_LEFT": False, "RUDDER_TRIM_RIGHT": False,
}


# ═══════════════════════════════════════════════════
# DLL 查找
# ═══════════════════════════════════════════════════

def find_simconnect_dll():
    """查找 SimConnect.dll 位置。

    搜索顺序：
      1. 本文件同目录
      2. 当前工作目录
      3. site-packages/SimConnect/（PySimConnect 安装路径）
      4. 系统 PATH（默认返回 "SimConnect.dll" 让 Windows 自动搜索）
    """
    for base in [os.path.dirname(__file__), os.getcwd()]:
        p = os.path.join(base, "SimConnect.dll")
        if os.path.exists(p):
            return p
    try:
        import site
        for d in site.getsitepackages():
            p = os.path.join(d, "SimConnect", "SimConnect.dll")
            if os.path.exists(p):
                return p
    except Exception:
        pass
    return "SimConnect.dll"


# ═══════════════════════════════════════════════════
# 高层封装
# ═══════════════════════════════════════════════════

class SimConnect:
    """SimConnect 原生封装 — 直接通过 ctypes WinDLL 调用 SimConnect.dll。

    特性：
    - 零 Python 依赖（仅 ctypes 标准库）
    - 完全控制 argtypes，无 Enum 类型污染
    - 线程安全的 dispatch 回调注册
    - 自动 DLL 查找

    用法:
        sc = SimConnect()
        sc.open("MyApp")
        # ... 使用各种方法 ...
        sc.close()
    """

    def __init__(self):
        self._dll = None
        self._hSimConnect = None
        self._dispatch_cb = None
        self._DispatchProc = None

    # ── 属性 ──────────────────────────────────────

    @property
    def handle(self):
        """SimConnect 句柄（HANDLE），未连接时为 None"""
        return self._hSimConnect

    @property
    def dll(self):
        """已加载的 WinDLL 对象，未加载时为 None"""
        return self._dll

    @property
    def is_open(self):
        """是否已成功打开连接"""
        return (self._hSimConnect is not None
                and self._hSimConnect.value is not None
                and self._hSimConnect.value != 0)

    # ── 初始化 ────────────────────────────────────

    def load_dll(self, dll_path=None):
        """加载 SimConnect.dll。

        Args:
            dll_path: DLL 路径，为 None 时自动查找。
        """
        path = dll_path or find_simconnect_dll()
        logger.info("加载 SimConnect.dll: %s", path)
        self._dll = WinDLL(path)
        self._setup_argtypes()

    def _setup_argtypes(self):
        """配置所有 SimConnect API 函数的 argtypes"""
        d = self._dll

        # SimConnect_Open
        d.SimConnect_Open.restype = HRESULT
        d.SimConnect_Open.argtypes = [POINTER(HANDLE), c_char_p, c_void_p, DWORD, HANDLE, DWORD]

        # SimConnect_Close
        d.SimConnect_Close.restype = HRESULT
        d.SimConnect_Close.argtypes = [HANDLE]

        # SimConnect_CallDispatch
        self._DispatchProc = ctypes.WINFUNCTYPE(None, c_void_p, DWORD, c_void_p)
        d.SimConnect_CallDispatch.restype = HRESULT
        d.SimConnect_CallDispatch.argtypes = [HANDLE, self._DispatchProc, c_void_p]

        # SimConnect_AddToDataDefinition
        d.SimConnect_AddToDataDefinition.restype = HRESULT
        d.SimConnect_AddToDataDefinition.argtypes = [
            HANDLE, DWORD, c_char_p, c_char_p, c_ulong, c_float, DWORD,
        ]

        # SimConnect_RequestDataOnSimObjectType
        d.SimConnect_RequestDataOnSimObjectType.restype = HRESULT
        d.SimConnect_RequestDataOnSimObjectType.argtypes = [
            HANDLE, DWORD, DWORD, DWORD, c_ulong,
        ]

        # SimConnect_SetDataOnSimObject
        d.SimConnect_SetDataOnSimObject.restype = HRESULT
        d.SimConnect_SetDataOnSimObject.argtypes = [
            HANDLE, DWORD, c_ulong, DWORD, DWORD, DWORD, c_void_p,
        ]

        # SimConnect_MapClientEventToSimEvent
        d.SimConnect_MapClientEventToSimEvent.restype = HRESULT
        d.SimConnect_MapClientEventToSimEvent.argtypes = [HANDLE, DWORD, c_char_p]

        # SimConnect_TransmitClientEvent
        d.SimConnect_TransmitClientEvent.restype = HRESULT
        d.SimConnect_TransmitClientEvent.argtypes = [HANDLE, c_ulong, DWORD, DWORD, DWORD, DWORD]

        # SimConnect_SubscribeToSystemEvent
        d.SimConnect_SubscribeToSystemEvent.restype = HRESULT
        d.SimConnect_SubscribeToSystemEvent.argtypes = [HANDLE, DWORD, c_char_p]

        # SimConnect_GetLastSentPacketID
        d.SimConnect_GetLastSentPacketID.restype = HRESULT
        d.SimConnect_GetLastSentPacketID.argtypes = [HANDLE, POINTER(DWORD)]

        # SimConnect_ClearDataDefinition
        d.SimConnect_ClearDataDefinition.restype = HRESULT
        d.SimConnect_ClearDataDefinition.argtypes = [HANDLE, DWORD]

    # ── 连接管理 ──────────────────────────────────

    def open(self, app_name=b"SimConnectApp", window_handle=None, fifo_size=0,
             window_event_handle=None, config_index=0):
        """建立与 MSFS 的 SimConnect 连接。

        Args:
            app_name: 应用名称（bytes）。
            window_handle: 窗口句柄，默认为 None。
            fifo_size: FIFO 大小，默认为 0。
            window_event_handle: 窗口事件句柄，默认为 None。
            config_index: 配置索引，默认为 0。

        Returns:
            HANDLE: SimConnect 句柄。

        Raises:
            ConnectionError: 连接失败或返回空句柄。
            RuntimeError: DLL 未加载，请先调用 load_dll()。
        """
        if not self._dll:
            raise RuntimeError("DLL 未加载，请先调用 load_dll()")

        hSim = HANDLE(0)
        err = self._dll.SimConnect_Open(
            ctypes.byref(hSim), app_name, window_handle, fifo_size,
            window_event_handle, config_index,
        )
        if err != 0:
            raise ConnectionError(
                f"SimConnect_Open 失败: HRESULT=0x{err:08x}"
            )
        if not hSim or hSim.value is None or hSim.value == 0:
            raise ConnectionError(
                "SimConnect_Open 返回空句柄 — MSFS 可能未运行"
            )
        self._hSimConnect = hSim
        return hSim

    def close(self):
        """关闭 SimConnect 连接。"""
        if self._dll and self._hSimConnect:
            try:
                self._dll.SimConnect_Close(self._hSimConnect)
            except Exception:
                pass
            self._hSimConnect = None

    # ── dispatch ──────────────────────────────────

    def call_dispatch(self, callback):
        """设置并调用 dispatch 回调处理 SimConnect 消息。

        Args:
            callback: 回调函数，签名 (pData, cbData, pContext) -> None。
                      其中 pData 是 c_void_p，指向 SIMCONNECT_RECV 结构体。
        """
        if not self._dll or not self._hSimConnect:
            return
        self._dispatch_cb = self._DispatchProc(callback)
        self._dll.SimConnect_CallDispatch(
            self._hSimConnect, self._dispatch_cb, None
        )

    def dispatch(self):
        """处理一次 SimConnect 消息队列。需要先通过 set_dispatch_cb() 设置回调。"""
        if not self._dll or not self._hSimConnect or not self._dispatch_cb:
            return
        self._dll.SimConnect_CallDispatch(
            self._hSimConnect, self._dispatch_cb, None
        )

    def set_dispatch_cb(self, callback):
        """设置 dispatch 回调函数（不触发调用）。

        Args:
            callback: 回调函数，签名 (pData, cbData, pContext) -> None。
        """
        self._dispatch_cb = self._DispatchProc(callback)

    # ── 数据定义 ──────────────────────────────────

    def add_to_data_definition(self, define_id, simvar_name, unit,
                                datatype=0, epsilon=0.0, datasize=0xFFFFFFFF):
        """注册 SimVar 数据定义。

        Args:
            define_id: 定义 ID（整数）。
            simvar_name: SimVar 名称（bytes），如 b"PLANE ALTITUDE"。
            unit: 单位（bytes），如 b"Feet"。
            datatype: 数据类型，默认 0（FLOAT64）。
            epsilon: 误差容限，默认 0.0。
            datasize: 数据大小，默认 SIMCONNECT_UNUSED。

        Returns:
            HRESULT 错误码，0 表示成功。
        """
        return self._dll.SimConnect_AddToDataDefinition(
            self._hSimConnect, DWORD(define_id), simvar_name, unit,
            c_ulong(datatype), c_float(epsilon), DWORD(datasize),
        )

    def clear_data_definition(self, define_id):
        """清除数据定义。"""
        return self._dll.SimConnect_ClearDataDefinition(
            self._hSimConnect, DWORD(define_id)
        )

    # ── 数据请求 ──────────────────────────────────

    def request_data_on_simobject_type(self, request_id, define_id,
                                        object_id=0, simobject_type=0):
        """请求指定类型的 SimObject 数据。

        Args:
            request_id: 请求 ID（整数）。
            define_id: 定义 ID（整数）。
            object_id: 对象 ID，默认 0。
            simobject_type: SimObject 类型，默认 SIMCONNECT_SIMOBJECT_TYPE_USER。
        """
        return self._dll.SimConnect_RequestDataOnSimObjectType(
            self._hSimConnect, DWORD(request_id), DWORD(define_id),
            DWORD(object_id), c_ulong(simobject_type),
        )

    # ── 数据写入 ──────────────────────────────────

    def set_data_on_simobject(self, define_id, simobject_type=0,
                               object_id=0, flags=0, datasize=8, data_ptr=None):
        """向 SimObject 写入数据。

        Args:
            define_id: 定义 ID（整数）。
            simobject_type: SimObject 类型，默认 SIMCONNECT_SIMOBJECT_TYPE_USER。
            object_id: 对象 ID，默认 0。
            flags: 标志，默认 0。
            datasize: 数据大小（字节），默认 8（double）。
            data_ptr: 数据指针（c_void_p），为 None 时跳过。
        """
        if data_ptr is None:
            return
        return self._dll.SimConnect_SetDataOnSimObject(
            self._hSimConnect, DWORD(define_id), c_ulong(simobject_type),
            DWORD(object_id), DWORD(flags), DWORD(datasize), data_ptr,
        )

    # ── 事件 ──────────────────────────────────────

    def map_client_event_to_sim_event(self, event_id, event_name):
        """将客户端事件 ID 映射到 Sim 事件名称。

        Args:
            event_id: 事件 ID（整数）。
            event_name: 事件名称（bytes），如 b"KEY_TOGGLE"。
        """
        return self._dll.SimConnect_MapClientEventToSimEvent(
            self._hSimConnect, DWORD(event_id), event_name,
        )

    def transmit_client_event(self, object_id=0, event_id=0, data=0,
                               group_priority=0x19000000, flags=16):
        """发送客户端事件到 SimObject。

        Args:
            object_id: 目标对象 ID，默认 SIMCONNECT_OBJECT_ID_USER。
            event_id: 事件 ID（整数）。
            data: 事件数据（整数）。
            group_priority: 组优先级，默认 0x19000000（STANDARD）。
            flags: 标志，默认 16（SIMCONNECT_EVENT_FLAG）。
        """
        return self._dll.SimConnect_TransmitClientEvent(
            self._hSimConnect, c_ulong(object_id), DWORD(event_id),
            DWORD(data), DWORD(group_priority), DWORD(flags),
        )

    # ── 系统事件 ──────────────────────────────────

    def subscribe_to_system_event(self, event_id, event_name):
        """订阅系统事件。

        Args:
            event_id: 事件 ID（整数）。
            event_name: 事件名称（bytes），如 b"SimStart"。
        """
        return self._dll.SimConnect_SubscribeToSystemEvent(
            self._hSimConnect, DWORD(event_id), event_name,
        )

    # ── 工具 ──────────────────────────────────────

    def get_last_sent_packet_id(self):
        """获取最后发送的数据包 ID。"""
        pid = DWORD(0)
        self._dll.SimConnect_GetLastSentPacketID(
            self._hSimConnect, ctypes.byref(pid)
        )
        return pid.value

    def read_double(self, pData):
        """从 dispatch 回调的 pData 中读取 double 值。

        用于 SIMCONNECT_RECV_ID_SIMOBJECT_DATA / _BYTYPE 消息。

        Args:
            pData: c_void_p，指向完整消息的指针。

        Returns:
            (request_id, float_value) 元组，解析失败返回 (None, None)。
        """
        try:
            obj = cast(pData, POINTER(FULL_SIMOBJECT_DATA)).contents
            addr = ctypes.addressof(obj.dwData)
            val = ctypes.cast(addr, POINTER(c_double)).contents.value
            return obj.dwRequestID, float(val)
        except Exception:
            return None, None
