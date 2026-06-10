"""SimConnect message structures (layout verified by tests)."""
from ctypes import Structure, sizeof as c_sizeof
from ctypes.wintypes import DWORD


class SIMCONNECT_RECV(Structure):
    """SimConnect 消息头部（所有消息的前 12 字节）"""

    _fields_ = [
        ("dwSize", DWORD),
        ("dwVersion", DWORD),
        ("dwID", DWORD),
    ]


class SIMOBJECT_DATA_HEADER(SIMCONNECT_RECV):
    """SIMCONNECT_RECV_SIMOBJECT_DATA 固定头部（含 dwData 起始 DWORD）。"""

    _fields_ = [
        ("dwRequestID", DWORD),
        ("dwObjectID", DWORD),
        ("dwDefineID", DWORD),
        ("dwFlags", DWORD),
        ("dwentrynumber", DWORD),
        ("dwoutof", DWORD),
        ("dwDefineCount", DWORD),
        ("dwData", DWORD),
    ]


SIMOBJECT_DATA_HEADER_SIZE = c_sizeof(SIMOBJECT_DATA_HEADER)
# SDK 示例以 &dwData 作为 payload 起点（12 + 7*DWORD = 40）
SIMOBJECT_DATA_PAYLOAD_OFFSET = c_sizeof(SIMCONNECT_RECV) + 7 * c_sizeof(DWORD)

# 向后兼容别名
FULL_SIMOBJECT_DATA = SIMOBJECT_DATA_HEADER


class SIMCONNECT_RECV_EVENT(SIMCONNECT_RECV):
    """SIMCONNECT_RECV_ID_EVENT 消息。"""

    _fields_ = [
        ("uGroupID", DWORD),
        ("uEventID", DWORD),
        ("dwData", DWORD),
    ]


class EXCEPTION_MSG(SIMCONNECT_RECV):
    """异常消息（含头部）"""

    _fields_ = [
        ("dwException", DWORD),
        ("dwSendID", DWORD),
        ("dwIndex", DWORD),
    ]


__all__ = [
    "SIMCONNECT_RECV",
    "SIMCONNECT_RECV_EVENT",
    "SIMOBJECT_DATA_HEADER",
    "SIMOBJECT_DATA_HEADER_SIZE",
    "SIMOBJECT_DATA_PAYLOAD_OFFSET",
    "FULL_SIMOBJECT_DATA",
    "EXCEPTION_MSG",
]
