# Architecture principles

> **One SimConnect message pump only. Struct layouts must match the MSFS SDK. Improve via serialized IO and reliable dispatch stop/start — not extra pumps or ctypes packing hacks.**

## Design constraints

| Do | Don't |
|---|---|
| Single pump thread (background `CallDispatch`) | Dual pump (foreground `get()` + background dispatch) |
| **Write queue**: `set`/`trigger` enqueue, pump thread drains | Multiple threads touching `hSimConnect` without serialization |
| `_io_lock` serializes DLL calls | Change ctypes struct `_pack_` (must match MSFS SDK layout) |
| `stop_background_dispatch() -> bool` + zombie/`force` recovery | Assume `CallDispatch` can be interrupted from Python |

## Write queue (v0.5.5+)

When background dispatch runs, `set()` / `trigger()` / `set_string()` are **auto-queued** and run on the pump thread between `CallDispatch` calls:

```python
sc.connect("MyApp")
sc.subscribe_many(FIELDS, on_data)

sc.set("AMBIENT TEMPERATURE", 18, "Celsius")
sc.trigger("WIND_DIRECTION_SET", 270)
```

`get()` does not pump when dispatch is already running — it waits on `_pending_get` events.

## Recommended connect order (many subscriptions)

```python
sc.connect("MyApp", start_dispatch=False)
sc.subscribe_many(FIELDS, on_data)
sc.start_background_dispatch()
```

## Health checks

```python
sc.dispatch_thread_alive
sc.dispatch_zombie
sc.is_dataflow_healthy(max_stale=2.0)
sc.restart_dispatch(force=True)
```

## String SimVars (MSFS)

TITLE / ATC TYPE etc. are **null-terminated C strings** on read; use `set_string()` for writes (STRINGV length prefix).

See also the [Cookbook](cookbook.md) sections on health checks and avoiding dual pumps.
