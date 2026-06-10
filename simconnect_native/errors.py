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


def check_hresult(code: int, operation: str, hint: str = "") -> int:
    if code != 0:
        raise SimConnectError(operation, code, hint)
    return code


__all__ = ["SimConnectError", "SimConnectTimeoutError", "check_hresult", "HRESULT_NAMES"]
