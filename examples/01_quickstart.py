"""Minimal quick start — read, subscribe, write, trigger."""
from __future__ import annotations

import time

from simconnect_native import DataField, SimConnect, SIMCONNECT_PERIOD_SIM_FRAME

FIELDS = {
    "alt": DataField("PLANE ALTITUDE", "feet"),
    "ias": DataField("AIRSPEED INDICATED", "knots"),
}


def main() -> None:
    with SimConnect.session("QuickStart") as sc:
        snapshot = sc.get_many(FIELDS, timeout=3.0)
        print("snapshot:", snapshot)

        def on_data(data):
            print("telemetry:", data)

        sc.subscribe_many(FIELDS, on_data, period=SIMCONNECT_PERIOD_SIM_FRAME)
        sc.set("GENERAL ENG THROTTLE LEVER POSITION:1", 0.5, "percent")
        sc.trigger("AP_MASTER")
        time.sleep(3)


if __name__ == "__main__":
    main()
