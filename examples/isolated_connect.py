"""Production pattern: SimConnect.dll in a killable child process.

    python examples/isolated_connect.py
"""
from simconnect_native import IsolatedSimConnect

FIELDS = {
    "alt": ("PLANE ALTITUDE", "feet"),
    "ias": ("AIRSPEED INDICATED", "knots"),
}


def main() -> None:
    iso = IsolatedSimConnect(heartbeat_timeout=8.0)
    try:
        iso.connect("IsolatedDemo", open_timeout=5.0, timeout=5.0)
        iso.subscribe_many(FIELDS, lambda d: print(d))
        input("Enter 退出（卡住时用 iso.kill()，不要 join native 线程）\n")
    except Exception as exc:
        print("connect failed:", exc)
        iso.kill()
    finally:
        iso.shutdown()


if __name__ == "__main__":
    main()
