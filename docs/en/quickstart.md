# Quick start

## Prerequisites

- **Windows** with MSFS installed
- **MSFS running**, aircraft loaded, **in flight**, simulation **not paused**
- Python 3.8+
- 64-bit `SimConnect.dll` (see [README](README.md#simconnectdll))

If reads time out, run `simconnect-h ping` or `python examples/diagnose_read.py`.

## Sync: session helper

```python
from simconnect_native import SimConnect, DataField

FIELDS = {
    "alt": DataField("PLANE ALTITUDE", "feet"),
    "ias": DataField("AIRSPEED INDICATED", "knots"),
    "hdg": DataField("PLANE HEADING DEGREES TRUE", "degrees"),
}

with SimConnect.session("MyApp") as sc:
    # One-shot batch read
    snapshot = sc.get_many(FIELDS, timeout=2.0)
    print(snapshot)

    # Live updates (20–50 Hz typical with SIM_FRAME)
    sc.subscribe_many(FIELDS, lambda d: print(d))

    # Write + event while subscribed (auto write queue)
    sc.set("GENERAL ENG THROTTLE LEVER POSITION:1", 0.5, "percent")
    sc.trigger("AP_MASTER")
```

`SimConnect.session()` connects, starts background dispatch, and closes on exit.

## Batch subscribe before dispatch

For many subscriptions, connect with `start_dispatch=False`, subscribe in a batch, then start dispatch once:

```python
from simconnect_native import SimConnect, SIMCONNECT_PERIOD_SIM_FRAME

FIELDS = {
    "alt": ("PLANE ALTITUDE", "feet"),
    "ias": ("AIRSPEED INDICATED", "knots"),
}

with SimConnect() as sc:
    sc.connect("Telemetry", start_dispatch=False)
    with sc.batch_subscribe():
        sc.subscribe_many(FIELDS, lambda d: print(d), period=SIMCONNECT_PERIOD_SIM_FRAME)
    # batch_subscribe exits → ensure_background_dispatch()
```

## Strings

**Mixed fields (v0.6.1+):** include string SimVars in `subscribe_many` / `get_many`:

```python
from simconnect_native import DataField

FIELDS = {
    "alt": DataField("PLANE ALTITUDE", "feet"),
    "title": DataField("TITLE", "", 11),  # STRINGV datatype
}

with SimConnect.session("MyApp") as sc:
    print(sc.get_many(FIELDS, timeout=2.0))
    sc.subscribe_many(FIELDS, lambda d: print(d))
```

Or read a string once:

```python
title = sc.get_string("TITLE", timeout=2.0)
```

## System events

```python
def on_pause(_):
    print("Sim paused")

sc.subscribe_system_event("Pause", on_pause)
```

## Asyncio

Uses the same single pump — sync calls run on the default executor:

```python
import asyncio
from simconnect_native import DataField
from simconnect_native.asyncio import AsyncSimConnect

async def main():
    fields = {
        "alt": DataField("PLANE ALTITUDE", "feet"),
        "ias": DataField("AIRSPEED INDICATED", "knots"),
    }
    async with AsyncSimConnect.session("AsyncApp") as asc:
        print(await asc.get_many(fields, timeout=3.0))
        async for packet in asc.subscribe_stream(fields):
            print(packet)

asyncio.run(main())
```

Full example: [`examples/async_quickstart.py`](../../examples/async_quickstart.py).

## CLI smoke test

```powershell
pip install -e .
simconnect-h ping
simconnect-h get "PLANE ALTITUDE" feet
simconnect-h watch "AIRSPEED INDICATED" knots --seconds 5
```

See [CLI reference](cli.md).

## Next steps

- [API reference](api.md)
- [Cookbook](cookbook.md) — `get` vs `subscribe`, deadlocks, FastAPI
- [Examples](../../examples/)
