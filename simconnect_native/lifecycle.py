"""Connection lifecycle hooks and batch subscribe helper."""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Callable, Iterator, Optional

logger = logging.getLogger(__name__)


class LifecycleMixin:
    """on_sim_start / on_aircraft_changed / batch_subscribe。"""

    on_sim_start: Optional[Callable[[], None]]
    on_aircraft_changed: Optional[Callable[[str], None]]
    on_dispatch_zombie: Optional[Callable[[], None]]

    _aircraft_track_sub_id: Optional[int]
    _last_aircraft_title: Optional[str]
    _aircraft_title_var: str

    def _init_lifecycle_hooks(self) -> None:
        self.on_sim_start = None
        self.on_aircraft_changed = None
        self.on_dispatch_zombie = None
        self._aircraft_track_sub_id = None
        self._last_aircraft_title = None
        self._aircraft_title_var = "TITLE"

    def _fire_sim_start_hooks(self, reason: str) -> None:
        cb = self.on_sim_start
        if not cb:
            return
        try:
            cb()
        except Exception as exc:
            logger.warning("on_sim_start(%s) 异常: %s", reason, exc)

    def _fire_dispatch_zombie_hook(self) -> None:
        cb = self.on_dispatch_zombie
        if not cb:
            return
        try:
            cb()
        except Exception as exc:
            logger.warning("on_dispatch_zombie 异常: %s", exc)

    @contextmanager
    def batch_subscribe(
        self,
        *,
        start_dispatch: bool = True,
    ) -> Iterator["LifecycleMixin"]:
        """批量 subscribe 后再启动 dispatch（退出 context 时 ensure）。"""
        try:
            yield self
        finally:
            if start_dispatch:
                self.ensure_background_dispatch()

    def enable_aircraft_change_detection(
        self,
        var_name: str = "TITLE",
        *,
        immediate_first: bool = False,
    ) -> int:
        """订阅 TITLE（默认），变化时调用 on_aircraft_changed。"""
        self._aircraft_title_var = var_name
        self._last_aircraft_title = None
        if self._aircraft_track_sub_id is not None:
            self.unsubscribe(self._aircraft_track_sub_id)
        self._aircraft_track_sub_id = self.subscribe_string(
            var_name,
            self._on_aircraft_title_update,
            immediate_first=immediate_first,
        )
        return self._aircraft_track_sub_id

    def disable_aircraft_change_detection(self) -> None:
        if self._aircraft_track_sub_id is not None:
            self.unsubscribe(self._aircraft_track_sub_id)
            self._aircraft_track_sub_id = None
        self._last_aircraft_title = None

    def _on_aircraft_title_update(self, title: str) -> None:
        prev = self._last_aircraft_title
        if prev is not None and title == prev:
            return
        self._last_aircraft_title = title
        cb = self.on_aircraft_changed
        if cb:
            try:
                cb(title)
            except Exception as exc:
                logger.warning("on_aircraft_changed 异常: %s", exc)

    def _bootstrap_string_subscription(
        self,
        var_name: str,
        callback: Callable[[str], None],
    ) -> None:
        """后台线程拉取首帧字符串，避免应用层轮询。"""

        def worker() -> None:
            try:
                value = self.get_string(var_name, timeout=2.0)
            except Exception as exc:
                logger.debug("subscribe_string 首帧读取失败 %s: %s", var_name, exc)
                return
            try:
                callback(value)
            except Exception as exc:
                logger.warning("subscribe_string 首帧回调异常: %s", exc)

        threading.Thread(
            target=worker,
            daemon=True,
            name=f"SimConnectBootstrap-{var_name}",
        ).start()
