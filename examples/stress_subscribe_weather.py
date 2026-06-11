"""Stress test: many subscriptions + concurrent weather writes.

MSFS 进入飞行后运行（需 SimConnect.dll）:

    pip install -e .
    python examples/stress_subscribe_weather.py

无 MSFS 时脚本会提示并退出。
"""
from __future__ import annotations

import logging
import sys
import threading
import time

from simconnect_native import SimConnect, SIMCONNECT_PERIOD_SIM_FRAME

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("stress")

# 40+ 数值 SimVar（与 ARL 仪表盘规模接近）
STRESS_FIELDS = {
    f"k{i}": (name, unit)
    for i, (name, unit) in enumerate([
        ("PLANE ALTITUDE", "feet"),
        ("AIRSPEED INDICATED", "knots"),
        ("VERTICAL SPEED", "feet per minute"),
        ("PLANE HEADING DEGREES TRUE", "degrees"),
        ("PLANE PITCH DEGREES", "degrees"),
        ("PLANE BANK DEGREES", "degrees"),
        ("GENERAL ENG RPM:1", "rpm"),
        ("GENERAL ENG THROTTLE LEVER POSITION:1", "percent"),
        ("FUEL TOTAL QUANTITY", "gallons"),
        ("AMBIENT TEMPERATURE", "celsius"),
        ("AMBIENT WIND VELOCITY", "knots"),
        ("AMBIENT WIND DIRECTION", "degrees"),
        ("AMBIENT PRESSURE", "millibars"),
        ("AMBIENT VISIBILITY", "meters"),
        ("G FORCE", "gforce"),
        ("INDICATED ALTITUDE", "feet"),
        ("KOHLSMAN SETTING HG", "inHg"),
        ("AUTOPILOT MASTER", "bool"),
        ("AUTOPILOT ALTITUDE LOCK VAR", "feet"),
        ("ELECTrical MASTER BATTERY", "bool"),
        ("FLAPS HANDLE INDEX", "number"),
        ("GEAR HANDLE POSITION", "bool"),
        ("BRAKE PARKING POSITION", "bool"),
        ("SIM ON GROUND", "bool"),
        ("GROUND VELOCITY", "knots"),
        ("TOTAL AIR TEMPERATURE", "celsius"),
        ("BAROMETER PRESSURE", "millibars"),
        ("MAGNETIC COMPASS", "degrees"),
        ("TURN COORDINATOR BALL", "position"),
        ("RADIO HEIGHT", "feet"),
        ("ACCELERATION BODY X", "feet per second squared"),
        ("ACCELERATION BODY Y", "feet per second squared"),
        ("ACCELERATION BODY Z", "feet per second squared"),
        ("RECIP ENG CHT:1", "celsius"),
        ("RECIP ENG OIL TEMPERATURE:1", "celsius"),
        ("RECIP ENG OIL PRESSURE:1", "psi"),
        ("FUEL LEFT QUANTITY", "gallons"),
        ("FUEL RIGHT QUANTITY", "gallons"),
        ("ELECTrical GENALT BUS VOLTAGE:1", "volts"),
        ("ELECTrical GENALT BUS AMPS:1", "amperes"),
        ("PITOT HEAT SWITCH", "bool"),
        ("WING FLEX PCT:1", "percent"),
        ("SPOILERS HANDLE POSITION", "percent"),
        ("YOKE X INDICATOR", "position"),
        ("YOKE Y INDICATOR", "position"),
    ])
}


def main() -> int:
    updates = {"n": 0}
    unhealthy = {"n": 0}

    def on_data(_d):
        updates["n"] += 1

    try:
        with SimConnect() as sc:
            sc.connect("StressWeather", start_dispatch=False)
            with sc.batch_subscribe():
                sc.subscribe_many(
                    STRESS_FIELDS,
                    on_data,
                    period=SIMCONNECT_PERIOD_SIM_FRAME,
                )
            logger.info("已订阅 %d 路 SimVar", len(STRESS_FIELDS))

            stop = threading.Event()

            def writer():
                i = 0
                while not stop.is_set():
                    try:
                        sc.weather_set_ambient(
                            wind_dir=float((270 + i) % 360),
                            temp_c=15.0 + float(i % 5),
                        )
                    except Exception as exc:
                        logger.debug("weather write: %s", exc)
                    i += 1
                    time.sleep(0.05)

            t = threading.Thread(target=writer, daemon=True, name="WeatherWriter")
            t.start()

            deadline = time.monotonic() + 15.0
            while time.monotonic() < deadline:
                if not sc.is_dataflow_healthy(max_stale=3.0):
                    unhealthy["n"] += 1
                time.sleep(0.5)

            stop.set()
            t.join(timeout=2.0)

            logger.info(
                "订阅回调 %d 次，不健康采样 %d 次，队列深度 %d",
                updates["n"],
                unhealthy["n"],
                sc.write_queue_depth,
            )

            if updates["n"] < 10:
                logger.error("订阅回调过少 — 数据流可能已断")
                return 1
            if unhealthy["n"] > 5:
                logger.error("is_dataflow_healthy 多次 False")
                return 1
            logger.info("压测通过")
            return 0
    except Exception as exc:
        logger.error("压测失败: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
