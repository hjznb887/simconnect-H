# simconnect-H

[Chinese](../../README.md) · **English**

> **Note:** If anything in the English docs conflicts with or omits detail from the Chinese README, **the Chinese documentation is authoritative**.

**Native Python SimConnect for MSFS** — zero pip runtime dependencies, `ctypes` only, PyInstaller-friendly (MIT).

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](../../LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)]()
[![Tests](https://github.com/hjznb887/simconnect-H/actions/workflows/test.yml/badge.svg)](https://github.com/hjznb887/simconnect-H/actions/workflows/test.yml)

**Docs:** [Cookbook](cookbook.md) · [Architecture](architecture.md) · [API](api.md) · [CHANGELOG](../../CHANGELOG.md)

---

## Quick start

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

Asyncio / FastAPI: [`examples/async_quickstart.py`](../../examples/async_quickstart.py), [`examples/fastapi_telemetry.py`](../../examples/fastapi_telemetry.py).

---

## Why use it

| | simconnect-H | Typical FSX-era wrappers |
|---|:---:|:---:|
| Dependencies | stdlib `ctypes` only | Third-party packages / old enums |
| MSFS `DATATYPE` | Matches SDK (`FLOAT64=4`) | Often wrong (`0`) |
| Connection | `connect()` one-liner | Manual `config_index` trial |
| High-frequency data | `subscribe_many` batch push | Polling `get()` |

## Features

- **Zero runtime deps** — copy the package or `pip install -e .`
- **One-shot connect** — find DLL, scan `config_index` 0–7, wait for OPEN, start dispatch
- **Three layers** — `get` / `set` / `subscribe` plus full ctypes surface
- **Batch subscribe** — dozens of SimVars in one `subscribe_many` (20–50 Hz telemetry)
- **Robust errors** — strict HRESULT checks, `SimConnectError`
- **Thread-safe** — single pump; no double-dispatch while background dispatch runs
- **Subscription health** — `subscription_healthy()`, throttled batch restore, outlier filtering (v0.7.0+)
- **CLI** — `simconnect-h get / set / watch / trigger / doctor / search` (182+ SimVar catalog)
- **Asyncio** — `AsyncSimConnect` + `subscribe_stream`; optional FastAPI telemetry example

## Install

```bash
git clone https://github.com/hjznb887/simconnect-H.git
cd simconnect-H
pip install -e .
```

Or copy [`simconnect_native/`](../../simconnect_native/) into your project.

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

## Documentation

| Page | Description |
|------|-------------|
| [Quick start](quickstart.md) | Sync + async patterns, strings, prerequisites |
| [API reference](api.md) | One-page table of public APIs |
| [Cookbook](cookbook.md) | Patterns, pitfalls, FastAPI bridge |
| [CLI](cli.md) | `simconnect-h` subcommands |
| [Architecture principles](architecture.md) | Single pump, write queue, SDK struct layout |

## Examples

| File | Description |
|------|-------------|
| [`examples/01_quickstart.py`](../../examples/01_quickstart.py) | Minimal sync session |
| [`examples/async_quickstart.py`](../../examples/async_quickstart.py) | Asyncio stream |
| [`examples/fastapi_telemetry.py`](../../examples/fastapi_telemetry.py) | REST + SSE (optional FastAPI) |
| [`examples/send_events.py`](../../examples/send_events.py) | Trigger MSFS events |
| [`examples/stress_subscribe.py`](../../examples/stress_subscribe.py) | 40+ subscriptions + concurrent writes |
| [`examples/diagnose_read.py`](../../examples/diagnose_read.py) | Connection diagnostics (`simconnect-h doctor`) |

Optional example deps: `pip install -r examples/requirements-examples.txt`

## Recent releases

Current version **v0.7.1**. Full history: [CHANGELOG.md](../../CHANGELOG.md).

### v0.7.1

- **Removed weather control API** — `WeatherMixin`, `weather.py`, and all `weather_set_*` methods (SimConnect weather control is unreliable)

### v0.7.0

- **Subscription health** — `subscription_healthy()` / `unhealthy_subscriptions()`; per-subscription auto-recovery
- **Data validation** — filter NaN / inf / extreme values on the dispatch path
- **Throttled batch restore** — reconnect restores in batches to reduce MSFS frame drops
- **Dispatch zombie hardening** — refuse a new pump thread while the old one is still alive

## Development

```powershell
python -m unittest discover -s tests -v
```

## License

[MIT License](../../LICENSE) — commercial and closed-source use allowed.
