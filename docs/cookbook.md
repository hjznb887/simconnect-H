# simconnect-H cookbook

## When to use `get` vs `subscribe`

| Pattern | API |
|---------|-----|
| Read once at startup | `get()` or `get_many()` |
| Dashboard / telemetry 20–50 Hz | `subscribe_many()` |
| Single value stream | `subscribe()` |

Do **not** loop `get()` at high frequency — each call is a round-trip.

## Write while subscribed

When background dispatch is running, `set()` and `trigger()` are **automatically queued** and drained on the pump thread. No need to stop dispatch.

## Avoid deadlocks

Never call `flush_write_queue()` while holding a lock that your subscription callback also needs. Use `WriteFuture.wait(timeout)` instead.

## After aircraft change

- `enable_aircraft_change_detection()` + `on_aircraft_changed`
- `mark_dataflow_quiet(8)` after load to avoid false unhealthy readings
- Subscriptions are restored automatically on OPEN / SimStart (2s debounced)

## Session helper

```python
from simconnect_native import SimConnect

with SimConnect.session("MyApp") as sc:
    alt = sc.get("PLANE ALTITUDE", "feet", timeout=2.0)
```

## CLI

```powershell
pip install -e .
simconnect-h ping
simconnect-h get "PLANE ALTITUDE" feet
simconnect-h watch "AIRSPEED INDICATED" knots --seconds 10
simconnect-h search altitude
```

## Asyncio

```python
from simconnect_native.asyncio import AsyncSimConnect

async with AsyncSimConnect.session("MyApp") as asc:
    data = await asc.get_many({"alt": ("PLANE ALTITUDE", "feet")})
    async for packet in asc.subscribe_stream({"alt": ("PLANE ALTITUDE", "feet")}):
        print(packet)
```

See [`examples/async_quickstart.py`](../examples/async_quickstart.py).
