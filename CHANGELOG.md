# Changelog

All notable changes to simconnect-H are documented here.

## [0.6.3] - 2026-06-17

### Changed

- Sync `docs/cookbook.md` with FastAPI bridge section; README links to cookbook
- Update architecture version table in `docs/simconnect-h-contribution.md`
- English docs link to architecture principles; FastAPI example type hint and startup note
- CI optional `fastapi-smoke` job

## [0.6.2] - 2026-06-17

### Added

- English documentation under `docs/en/` (README, quickstart, API, cookbook, CLI)
- `examples/fastapi_telemetry.py` — REST snapshot + SSE stream via `AsyncSimConnect`
- `examples/requirements-examples.txt` — optional FastAPI / uvicorn for examples only

## [0.6.1] - 2026-06-16

### Added

- Expanded `common_simvars.json` (~200 entries) and `common_events.json` for CLI search
- CLI `search` covers SimVars and events; shows recommended unit/datatype; `get` auto-fills unit from catalog
- `subscribe_many` supports mixed numeric + string fields (merged `{key: value}` callback)
- `simconnect_native.asyncio` module: `AsyncSimConnect` with `await get()`, `get_many()`, `subscribe_stream()`
- Bugfix: `get_many` uses dedicated ID range 20000+; `SimStart` system event uses ID 90001; `cmd_doctor` propagates exit code

### Changed

- Removed debug instrumentation from `sync_io.py`

## [0.6.0] - 2026-06-16

### Added

- `get_many()` — batch synchronous read returning `{key: value}`
- `DataField` helper type for field definitions
- `subscribe_system_event()` — Pause, SimStop, AircraftLoaded, etc.
- `SimConnect.session()` context manager for one-line connect
- `simconnect-h` CLI: `ping`, `get`, `set`, `watch`, `trigger`, `doctor`, `search`
- CI unittest workflow on Windows, `py.typed`, this CHANGELOG
- `examples/01_quickstart.py`, `examples/send_events.py`, `examples/stress_subscribe.py`
- `docs/cookbook.md`

### Changed

- Weather API documented as legacy (MSFS 2020 unreliable via SimConnect)
- README English quick start; expanded PyPI description
- Development status: Beta
- `subscribe_many` uses shared `fields` module with `get_many`

### Deprecated

- `examples/stress_subscribe_weather.py` — use `stress_subscribe.py`

## [0.5.8] and earlier

See [README.md](README.md) version history section.
