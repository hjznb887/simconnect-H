"""Shared ctypes helpers."""
from __future__ import annotations

import ctypes
from typing import Any

from ctypes import c_long, c_ulong
from ctypes.wintypes import DWORD

try:
    from ctypes.wintypes import HRESULT
except ImportError:
    HRESULT = c_long

_WinDLL = getattr(ctypes, "WinDLL", None)


def ctypes_value(value: Any) -> Any:
    """Return the Python value stored in a ctypes scalar."""
    return value.value if hasattr(value, "value") else value


def as_int(value: Any) -> int:
    return int(ctypes_value(value))


def as_dword(value: Any) -> DWORD:
    return DWORD(as_int(value))


def as_c_ulong(value: Any) -> c_ulong:
    return c_ulong(as_int(value))


def is_bare_dll_name(path: str) -> bool:
    """True when Windows can resolve the DLL through the standard search path."""
    return "/" not in path and "\\" not in path and ":" not in path


def as_non_negative_int(name: str, value: int) -> int:
    """高层 API 参数校验：非负 int（不含 bool）。"""
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be int, got {type(value).__name__}")
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value}")
    return value
