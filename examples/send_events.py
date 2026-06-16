"""Subscribe to MSFS system events (Pause, SimStop, etc.)."""
from __future__ import annotations

import time

from simconnect_native import SimConnect


def main() -> None:
    with SimConnect.session("SystemEvents") as sc:

        def on_event(name: str, data: int) -> None:
            print(f"event {name!r} data={data}")

        sc.subscribe_system_event("Pause", on_event)
        sc.subscribe_system_event("Unpause", on_event)
        sc.subscribe_system_event("SimStop", on_event)
        print("Listening for Pause / Unpause / SimStop (Ctrl+C to exit)...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
