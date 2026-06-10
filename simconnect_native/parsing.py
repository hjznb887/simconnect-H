"""Parse SimConnect dispatch payloads."""
from __future__ import annotations

import ctypes
from typing import Any, Optional, Tuple

from ctypes import (
    POINTER,
    c_double,
    c_float,
    c_int32,
    c_int64,
    c_void_p,
    cast,
)

from .constants import EXCEPTION_NAMES
from .structures import (
    EXCEPTION_MSG,
    SIMOBJECT_DATA_HEADER,
)
from .utils import as_int

DATATYPE_SIZES = {
    1: 4,   # INT32
    2: 8,   # INT64
    3: 4,   # FLOAT32
    4: 8,   # FLOAT64
}


def payload_base(p_data: Any) -> Optional[int]:
    """与 SDK 示例 &pObjData->dwData 一致（基址 + offsetof(dwData)）。"""
    if not p_data:
        return None
    return cast(p_data, c_void_p).value + SIMOBJECT_DATA_HEADER.dwData.offset


def read_data_at(base_addr: int, datatype: int = 4) -> Any:
    datatype = as_int(datatype)
    if datatype == 4:
        return ctypes.cast(base_addr, POINTER(c_double)).contents.value
    if datatype == 3:
        return ctypes.cast(base_addr, POINTER(c_float)).contents.value
    if datatype == 1:
        return ctypes.cast(base_addr, POINTER(c_int32)).contents.value
    if datatype == 2:
        return ctypes.cast(base_addr, POINTER(c_int64)).contents.value
    if datatype == 11:
        str_len = ctypes.cast(base_addr, POINTER(c_int32)).contents.value
        if str_len <= 0 or str_len > 4096:
            return None
        str_addr = base_addr + 4
        buf = ctypes.cast(str_addr, POINTER(ctypes.c_char * str_len)).contents
        return buf.value.decode("utf-8", errors="replace")
    return None


def simobject_data_has_payload(
    header: SIMOBJECT_DATA_HEADER,
    datatype: int = 4,
    define_count: Optional[int] = None,
) -> bool:
    """仅检查 dwDefineCount；MSFS 常设 dwSize=44（头部大小），数据仍在 dwData 之后。"""
    count = int(header.dwDefineCount) if define_count is None else int(define_count)
    return count >= 1


def read_double(p_data: Any) -> Tuple[Optional[int], Optional[float]]:
    """从 SIMOBJECT_DATA 消息读取 (request_id, float64)。"""
    try:
        if not p_data:
            return None, None
        header = cast(p_data, POINTER(SIMOBJECT_DATA_HEADER)).contents
        req_id = int(header.dwRequestID)
        if not simobject_data_has_payload(header, 4):
            return req_id, None
        base = payload_base(p_data)
        if base is None:
            return req_id, None
        val = cast(base, POINTER(c_double)).contents.value
        return req_id, float(val)
    except Exception:
        return None, None


def read_data(p_data: Any, datatype: int = 4) -> Any:
    """从 SIMOBJECT_DATA 消息按 datatype 读取 payload（首个字段）。"""
    try:
        if not p_data:
            return None
        header = cast(p_data, POINTER(SIMOBJECT_DATA_HEADER)).contents
        if not simobject_data_has_payload(header, datatype):
            return None
        base = payload_base(p_data)
        if base is None:
            return None
        return read_data_at(base, datatype)
    except Exception:
        return None


def parse_exception(
    p_data: Any,
) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """解析 SIMCONNECT_RECV_ID_EXCEPTION 消息。"""
    try:
        if not p_data:
            return None, None, None
        exc = cast(p_data, POINTER(EXCEPTION_MSG)).contents
        name = EXCEPTION_NAMES.get(exc.dwException, f"UNKNOWN({exc.dwException})")
        return name, exc.dwSendID, exc.dwIndex
    except Exception:
        return None, None, None
