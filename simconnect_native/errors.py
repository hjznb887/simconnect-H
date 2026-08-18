"""SimConnect error types."""
from __future__ import annotations

from .constants import HRESULT_NAMES


class SimConnectError(Exception):
    """SimConnect API 调用失败。"""

    def __init__(self, operation: str, code: int, hint: str = "") -> None:
        self.operation = operation
        self.code = int(code)
        self.hint = hint
        name = HRESULT_NAMES.get(self.code, "")
        msg = f"{operation} failed: HRESULT=0x{self.code:08x}"
        if name:
            msg += f" ({name})"
        if hint:
            msg += f" — {hint}"
        super().__init__(msg)


class SimConnectTimeoutError(SimConnectError):
    """同步读超时。"""

    def __init__(self, operation: str, timeout: float, hint: str = "") -> None:
        self.timeout = timeout
        super().__init__(
            operation,
            0,
            hint or f"no response within {timeout}s",
        )


class SimConnectWriteTimeoutError(SimConnectError):
    """写入队列等待超时。"""

    def __init__(self, operation: str, timeout: float, hint: str = "") -> None:
        self.timeout = timeout
        super().__init__(
            operation,
            0,
            hint or f"write not completed within {timeout}s",
        )


class SimConnectOpenTimeoutError(SimConnectTimeoutError):
    """SimConnect_Open 在超时内未返回（DLL 线程可能已钉死）。"""


class SimConnectNativeHungError(SimConnectError):
    """进程内 native 调用已卡住，无法在同一进程恢复。"""

    def __init__(self, operation: str = "native", hint: str = "") -> None:
        super().__init__(
            operation,
            0,
            hint
            or "SimConnect.dll thread is hung; kill IsolatedSimConnect worker or the host process",
        )


def check_hresult(code: int, operation: str, hint: str = "") -> int:
    if code != 0:
        raise SimConnectError(operation, code, hint)
    return code


__all__ = [
    "SimConnectError",
    "SimConnectTimeoutError",
    "SimConnectWriteTimeoutError",
    "SimConnectOpenTimeoutError",
    "SimConnectNativeHungError",
    "check_hresult",
    "HRESULT_NAMES",
]
