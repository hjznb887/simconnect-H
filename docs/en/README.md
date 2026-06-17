# simconnect-H

[Chinese](../../README.md) · **English**

**Native Python SimConnect for MSFS** — zero pip runtime dependencies, `ctypes` only, PyInstaller-friendly (MIT).

## Why use it

| | simconnect-H | Typical FSX-era wrappers |
|---|:---:|:---:|
| Dependencies | stdlib `ctypes` only | Third-party packages / old enums |
| MSFS `DATATYPE` | Matches SDK (`FLOAT64=4`) | Often wrong (`0`) |
| Connection | `connect()` one-liner | Manual `config_index` trial |
| High-frequency data | `subscribe_many` batch push | Polling `get()` |

**Highlights:** auto-reconnect, write queue on the pump thread, single message pump (thread-safe), `simconnect-h` CLI, asyncio bridge (`AsyncSimConnect`).

## Install

```bash
git clone https://github.com/hjznb887/simconnect-H.git
cd simconnect-H
pip install -e .
```

Or copy the [`simconnect_native/`](../../simconnect_native/) folder into your project.

### SimConnect.dll

You need the **64-bit** MSFS SDK redistributable `SimConnect.dll`. Lookup order:

1. Environment variable `SIMCONNECT_DLL`
2. Portable exe directory / `lib\SimConnect.dll`
3. **MSFS game folder** (Steam / Microsoft Store — same version as the running sim)
4. Bundled `simconnect_native/lib/SimConnect.dll`
5. MSFS SDK install path

```powershell
# Optional: copy SDK DLL into the package
scripts\copy_simconnect_dll.ps1
```

Do **not** replace with FSX or PySimConnect DLLs.

## 5-minute quick start

MSFS running, in flight, **not paused**:

```python
from simconnect_native import SimConnect, DataField

FIELDS = {
    "alt": DataField("PLANE ALTITUDE", "feet"),
    "ias": DataField("AIRSPEED INDICATED", "knots"),
}

with SimConnect.session("MyApp") as sc:
    print(sc.get_many(FIELDS, timeout=2.0))
    sc.subscribe_many(FIELDS, lambda d: print(d))
    sc.set("GENERAL ENG THROTTLE LEVER POSITION:1", 0.5, "percent")
    sc.trigger("AP_MASTER")
```

```powershell
pip install -e .
simconnect-h ping
simconnect-h get "PLANE ALTITUDE" feet
```

Asyncio:

```python
from simconnect_native.asyncio import AsyncSimConnect

async with AsyncSimConnect.session("MyApp") as asc:
    alt = await asc.get("PLANE ALTITUDE", "feet")
    async for data in asc.subscribe_stream({"alt": ("PLANE ALTITUDE", "feet")}):
        print(data)
```

## Documentation

| Page | Description |
|------|-------------|
| [Quick start](quickstart.md) | Sync + async patterns, strings, prerequisites |
| [API reference](api.md) | One-page table of public APIs |
| [Cookbook](cookbook.md) | Patterns, pitfalls, FastAPI bridge |
| [CLI](cli.md) | `simconnect-h` subcommands |
| [Architecture principles](architecture.md) | Single pump, write queue, SDK struct layout |

## Examples

- [`examples/01_quickstart.py`](../../examples/01_quickstart.py) — minimal sync session
- [`examples/async_quickstart.py`](../../examples/async_quickstart.py) — asyncio stream
- [`examples/fastapi_telemetry.py`](../../examples/fastapi_telemetry.py) — REST + SSE (optional FastAPI)
- [`examples/send_events.py`](../../examples/send_events.py) — trigger events
- [`examples/stress_subscribe.py`](../../examples/stress_subscribe.py) — 40+ subscriptions

Install example-only deps: `pip install -r examples/requirements-examples.txt`

## Not recommended

**Weather control** (`weather_set_mode_custom`, `weather_set_observation`, etc.) is kept for compatibility only. MSFS 2020 weather via SimConnect is unreliable — do not build new features on it.
