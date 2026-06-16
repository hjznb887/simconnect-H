"""Asyncio bridge over sync SimConnect (single pump unchanged)."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import TracebackType
from typing import Any, AsyncIterator, Dict, Optional, Type

from .client import SimConnect
from .fields import FieldsMapping


class AsyncSimConnect:
    """Thin asyncio wrapper — runs sync SimConnect on the default executor."""

    def __init__(self, sc: SimConnect, loop: asyncio.AbstractEventLoop):
        self._sc = sc
        self._loop = loop

    @property
    def sync(self) -> SimConnect:
        """Underlying sync client (advanced use)."""
        return self._sc

    @classmethod
    async def connect(
        cls,
        app_name: str = "AsyncSimConnect",
        *,
        auto_reconnect: bool = True,
        **connect_kwargs: Any,
    ) -> "AsyncSimConnect":
        loop = asyncio.get_running_loop()
        sc = SimConnect(auto_reconnect=auto_reconnect)

        def _open() -> None:
            sc.connect(app_name, **connect_kwargs)

        await loop.run_in_executor(None, _open)
        return cls(sc, loop)

    @classmethod
    @asynccontextmanager
    async def session(
        cls,
        app_name: str = "AsyncSimConnect",
        *,
        auto_reconnect: bool = True,
        **connect_kwargs: Any,
    ) -> AsyncIterator["AsyncSimConnect"]:
        inst = await cls.connect(
            app_name, auto_reconnect=auto_reconnect, **connect_kwargs,
        )
        try:
            yield inst
        finally:
            await inst.close()

    async def close(self) -> None:
        await self._loop.run_in_executor(None, self._sc.close)

    async def __aenter__(self) -> "AsyncSimConnect":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        await self.close()

    async def get(
        self,
        var_name: str,
        unit: str,
        timeout: float = 2.0,
        **kwargs: Any,
    ) -> Any:
        return await self._loop.run_in_executor(
            None,
            lambda: self._sc.get(var_name, unit, timeout=timeout, **kwargs),
        )

    async def get_string(self, var_name: str, timeout: float = 2.0) -> str:
        return await self._loop.run_in_executor(
            None,
            lambda: self._sc.get_string(var_name, timeout=timeout),
        )

    async def get_many(
        self,
        fields: FieldsMapping,
        timeout: float = 0.5,
    ) -> Dict[str, Any]:
        return await self._loop.run_in_executor(
            None,
            lambda: self._sc.get_many(fields, timeout=timeout),
        )

    async def set(
        self,
        var_name: str,
        value: Any,
        unit: str,
        **kwargs: Any,
    ) -> None:
        await self._loop.run_in_executor(
            None,
            lambda: self._sc.set(var_name, value, unit, **kwargs),
        )

    async def trigger(self, event_name: str, data: int = 0) -> None:
        await self._loop.run_in_executor(
            None,
            lambda: self._sc.trigger(event_name, data),
        )

    async def subscribe_stream(
        self,
        fields: FieldsMapping,
        period: Optional[int] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Async iterator over subscribe_many / mixed field updates."""
        from .constants import SIMCONNECT_PERIOD_SIM_FRAME_INT

        if period is None:
            period = SIMCONNECT_PERIOD_SIM_FRAME_INT

        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        loop = self._loop

        def on_data(data: Dict[str, Any]) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, data)

        sub_id = self._sc.subscribe_many(fields, on_data, period=period)
        try:
            while True:
                yield await queue.get()
        finally:
            await loop.run_in_executor(
                None, lambda: self._sc.unsubscribe(sub_id),
            )

    async def subscribe_collect(
        self,
        fields: FieldsMapping,
        *,
        count: int = 1,
        period: Optional[int] = None,
    ) -> list:
        """Collect N subscription packets then auto-unsubscribe."""
        results = []
        async for packet in self.subscribe_stream(fields, period=period):
            results.append(packet)
            if len(results) >= count:
                break
        return results
