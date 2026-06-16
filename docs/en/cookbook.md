# Cookbook

## When to use `get` vs `subscribe`

| Pattern | API |
|---------|-----|
| Read once at startup | `get()` or `get_many()` |
| Dashboard / telemetry 20–50 Hz | `subscribe_many()` |
| Single value stream | `subscribe()` |

Do **not** loop `get()` at high frequency — each call is a round-trip.

## Write while subscribed

When background dispatch is running, `set()` and `trigger()` are **automatically queued** and drained on the pump thread. No need to stop dispatch.

```python
sc.set("GENERAL ENG THROTTLE LEVER POSITION:1", 0.75, "percent")
sc.trigger("AP_MASTER")
```

For async completion:

```python
fut = sc.submit_set("GENERAL ENG THROTTLE LEVER POSITION:1", 0.75, "percent")
fut.wait(timeout=2.0)
```

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

## Mixed numeric + string subscriptions

```python
from simconnect_native import DataField

fields = {
    "ias": DataField("AIRSPEED INDICATED", "knots"),
    "title": DataField("TITLE", "", 11),
}
sc.subscribe_many(fields, lambda d: print(d))
```

## CLI

```powershell
pip install -e .
simconnect-h ping
simconnect-h get "PLANE ALTITUDE" feet
simconnect-h watch "AIRSPEED INDICATED" knots --seconds 10
simconnect-h search altitude
simconnect-h search ap --events-only
```

## Asyncio

```python
from simconnect_native.asyncio import AsyncSimConnect

async with AsyncSimConnect.session("MyApp") as asc:
    data = await asc.get_many({"alt": ("PLANE ALTITUDE", "feet")})
    async for packet in asc.subscribe_stream({"alt": ("PLANE ALTITUDE", "feet")}):
        print(packet)
```

See [`examples/async_quickstart.py`](../../examples/async_quickstart.py).

## FastAPI bridge

Expose telemetry over HTTP without a second SimConnect pump. The example uses `AsyncSimConnect` with a single app lifespan connection.

**Endpoints:**

| Route | Description |
|-------|-------------|
| `GET /health` | Liveness (no MSFS) |
| `GET /snapshot` | JSON snapshot via `get_many` |
| `GET /stream` | Server-Sent Events from `subscribe_stream` |

**Run:**

```powershell
pip install -e .
pip install -r examples/requirements-examples.txt
# MSFS in flight:
uvicorn examples.fastapi_telemetry:app --host 127.0.0.1 --port 8765
```

Then open `http://127.0.0.1:8765/snapshot` or stream with:

```powershell
curl -N http://127.0.0.1:8765/stream
```

If MSFS is not connected, `/snapshot` and `/stream` return **503** with a JSON error message.

Source: [`examples/fastapi_telemetry.py`](../../examples/fastapi_telemetry.py).

## Health checks

Do not rely only on `_dispatch_running`. Use `is_dataflow_healthy()` or check `dispatch_zombie` after `stop_background_dispatch()`.

## Do not run two pumps

When background dispatch is active, `get()` waits on events — it does not call `dispatch()` again. For sync I/O that must exclude the pump, use `with_paused_dispatch()`.
