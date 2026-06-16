# API reference

One-page overview of common public APIs. Full signatures are in source docstrings.

Import:

```python
from simconnect_native import SimConnect, DataField, SimConnectError
from simconnect_native.asyncio import AsyncSimConnect
```

## Connection

| API | Description |
|-----|-------------|
| `SimConnect.connect(app_name, ...)` | Connect, find DLL, scan `config_index`, start dispatch |
| `SimConnect.session(app_name)` | Context manager: connect + close |
| `SimConnect.load_dll(path=None)` | Load `SimConnect.dll` |
| `SimConnect.open(...)` / `close()` | Low-level open / close |
| `SimConnect.start_background_dispatch()` | Start message pump (auto-reconnect) |
| `SimConnect.stop_background_dispatch(timeout=5.0, force=False)` | Stop pump; returns whether thread exited |
| `SimConnect.is_dataflow_healthy(max_stale=2.0)` | Dispatch running and recent subscription data |
| `SimConnect.dispatch_thread_alive` / `dispatch_zombie` | Thread state flags |
| `SimConnect.mark_dataflow_quiet(seconds=8)` | Grace window after aircraft change |
| `SimConnect.with_paused_dispatch()` | Pause pump for sync I/O |
| `SimConnect.ensure_background_dispatch()` | Start dispatch if not running |

## Read / write

| API | Description |
|-----|-------------|
| `get(var, unit, timeout=0.1)` | Sync read one numeric SimVar |
| `get_many(fields, timeout=0.5)` | Batch sync read → `{key: value}` |
| `get_string(var, timeout=1.0)` | Sync read string SimVar |
| `set(var, value, unit)` | Write SimVar (queued when dispatch runs) |
| `set_string(var, value)` | Write string SimVar |
| `submit_set(...)` / `submit_trigger(...)` | Enqueue write; returns `WriteFuture` |
| `submit(callable)` | Enqueue custom write on pump thread |
| `flush_write_queue(timeout=5.0)` | Wait for queue drain |
| `write_queue_depth` / `write_queue_enabled` | Queue introspection |
| `trigger(event_name, data=0)` | Fire MSFS event |

`fields` accepts `DataField`, `(name, unit)` tuples, or `(name, unit, datatype)` for strings.

## Subscribe

| API | Description |
|-----|-------------|
| `subscribe(var, unit, callback, period=SIM_FRAME)` | Single numeric SimVar |
| `subscribe_string(var, callback, period=SIM_FRAME)` | String SimVar |
| `subscribe_many(fields, callback, period=SIM_FRAME)` | Batch; numeric + string mixed (v0.6.1+) |
| `unsubscribe(sub_id)` | Cancel subscription |
| `batch_subscribe()` | Context: auto `ensure_background_dispatch()` after block |
| `subscribe_system_event(name, callback)` | Pause, SimStop, SimStart, etc. |

## Lifecycle hooks

| Member | Description |
|--------|-------------|
| `on_sim_start` | Called on OPEN / SimStart / ASSIGNED_OBJECT_ID |
| `on_aircraft_changed` | With `enable_aircraft_change_detection()` |
| `on_dispatch_zombie` | Pump stop timed out |
| `enable_aircraft_change_detection()` | Subscribe TITLE; fires on aircraft change |

## Async (`simconnect_native.asyncio`)

| API | Description |
|-----|-------------|
| `AsyncSimConnect.connect(app_name, ...)` | Async connect |
| `AsyncSimConnect.session(app_name)` | Async context manager |
| `await asc.get(var, unit, timeout=2.0)` | Executor-backed read |
| `await asc.get_string(var, timeout=2.0)` | String read |
| `await asc.get_many(fields, timeout=0.5)` | Batch read |
| `await asc.set(var, value, unit)` | Write |
| `await asc.trigger(event_name, data=0)` | Event |
| `async for d in asc.subscribe_stream(fields)` | Async iterator over `subscribe_many` |
| `await asc.subscribe_collect(fields, count=1)` | Collect N packets then unsubscribe |
| `asc.sync` | Underlying `SimConnect` instance |

## CLI (`simconnect-h`)

| Command | Description |
|---------|-------------|
| `ping` | Test connection (read altitude) |
| `get VAR [UNIT]` | Read one SimVar (`--string`, `--timeout`) |
| `set VAR VALUE [UNIT]` | Write one SimVar |
| `watch VAR [UNIT]` | Subscribe and print (`--seconds`) |
| `trigger EVENT [DATA]` | Trigger event |
| `search QUERY` | Search catalog (`--events-only`, `--simvars-only`, `--limit`) |
| `doctor` | Run `examples/diagnose_read.py` |

See [cli.md](cli.md).

## Constants

```python
from simconnect_native import (
    SIMCONNECT_DATATYPE_FLOAT64,   # 4 — default numeric
    SIMCONNECT_DATATYPE_STRINGV,   # 11 — TITLE etc.
    SIMCONNECT_PERIOD_SIM_FRAME,   # per sim frame
    SIMCONNECT_PERIOD_VISUAL_FRAME,
    SimConnectError,
)
```

Full list: [`simconnect_native/constants.py`](../../simconnect_native/constants.py).

## Legacy (not recommended)

`weather_set_mode_custom`, `weather_set_observation`, `weather_apply_metar`, `weather_set_ambient` — MSFS 2020 weather via SimConnect is unreliable.
