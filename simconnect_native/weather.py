"""MSFS weather helpers (SimConnect world functions)."""
from __future__ import annotations

from typing import Optional, Union

from .errors import check_hresult


class WeatherMixin:
    """weather_set_* — METAR/模式走 paused dispatch；滑块类用 set()。"""

    def weather_set_mode_custom(self, *, write_timeout: float = 5.0) -> None:
        """切换为自定义天气模式（SimConnect_WeatherSetModeCustom）。"""
        if not self.is_open:
            raise RuntimeError("SimConnect 未连接，请先调用 open()")
        if self._should_use_write_queue() and not self._is_dispatch_thread():
            self.submit(
                lambda sc: sc._weather_set_mode_custom_direct(),
                label="weather_set_mode_custom",
            ).result_or_raise(write_timeout)
            return
        self._weather_set_mode_custom_direct()

    def weather_set_observation(
        self,
        metar: Union[bytes, str],
        seconds: int = 0,
        *,
        write_timeout: float = 5.0,
    ) -> None:
        """设置 METAR（SimConnect_WeatherSetObservation）。建议配合 weather_apply_metar()。"""
        if not self.is_open:
            raise RuntimeError("SimConnect 未连接，请先调用 open()")
        metar_b = metar.encode("utf-8") if isinstance(metar, str) else metar
        if self._should_use_write_queue() and not self._is_dispatch_thread():
            self.submit(
                lambda sc: sc._weather_set_observation_direct(metar_b, seconds),
                label="weather_set_observation",
            ).result_or_raise(write_timeout)
            return
        self._weather_set_observation_direct(metar_b, seconds)

    def weather_apply_metar(
        self,
        metar: Union[bytes, str],
        seconds: int = 0,
        *,
        stop_timeout: float = 5.0,
    ) -> None:
        """METAR + ModeCustom；批量天气写入，自动 paused dispatch。"""
        with self.with_paused_dispatch(stop_timeout=stop_timeout):
            metar_b = metar.encode("utf-8") if isinstance(metar, str) else metar
            self._weather_set_observation_direct(metar_b, seconds)
            self._weather_set_mode_custom_direct()

    def weather_set_ambient(
        self,
        *,
        wind_dir: Optional[float] = None,
        wind_kt: Optional[float] = None,
        temp_c: Optional[float] = None,
        pressure_hpa: Optional[float] = None,
        visibility_m: Optional[float] = None,
        write_timeout: float = 5.0,
    ) -> None:
        """设置环境天气 SimVar（单参数滑块类，走 set/写入队列）。"""
        if wind_dir is not None:
            self.set("AMBIENT WIND DIRECTION", wind_dir, "degrees", write_timeout=write_timeout)
        if wind_kt is not None:
            self.set("AMBIENT WIND VELOCITY", wind_kt, "knots", write_timeout=write_timeout)
        if temp_c is not None:
            self.set("AMBIENT TEMPERATURE", temp_c, "celsius", write_timeout=write_timeout)
        if pressure_hpa is not None:
            self.set("AMBIENT PRESSURE", pressure_hpa, "millibars", write_timeout=write_timeout)
        if visibility_m is not None:
            self.set("AMBIENT VISIBILITY", visibility_m, "meters", write_timeout=write_timeout)

    def _weather_set_mode_custom_direct(self) -> None:
        check_hresult(
            self._dll_weather_set_mode_custom(),
            "WeatherSetModeCustom",
        )

    def _weather_set_observation_direct(self, metar: bytes, seconds: int) -> None:
        check_hresult(
            self._dll_weather_set_observation(int(seconds), metar),
            "WeatherSetObservation",
        )

    def _dll_weather_set_mode_custom(self) -> int:
        with self._io_lock:
            return self._dll.SimConnect_WeatherSetModeCustom(self._hSimConnect)

    def _dll_weather_set_observation(self, seconds: int, metar: bytes) -> int:
        from .utils import as_dword

        with self._io_lock:
            return self._dll.SimConnect_WeatherSetObservation(
                self._hSimConnect,
                as_dword(seconds),
                metar,
            )
