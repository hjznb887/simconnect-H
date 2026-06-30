# Changelog

All notable changes to simconnect-H are documented here.

## [0.7.1] - 2026-06-30

### Removed

- **Weather control API**: removed `weather.py`, `WeatherMixin`, and all weather set/observe methods.
  - Deleted `simconnect_native/weather.py` and `examples/stress_subscribe_weather.py`
  - Removed `WeatherMixin` from `client.py` import and class inheritance
  - Removed DLL function signatures for `SimConnect_WeatherSetModeCustom` / `SimConnect_WeatherSetObservation`
  - Replaced `tests/test_weather_lifecycle.py` with `tests/test_lifecycle.py` (lifecycle hooks only)
- **Documentation**: removed all weather sections from `README.md`, `docs/en/README.md`, `docs/en/api.md`

## [0.7.0] - 2026-06-24

### Added

- **Per-subscription health tracking** (`subscribe.py`): each subscription tracks its last callback
  timestamp. New public API:
  - `subscription_healthy(sub_id, max_stale=15.0) -> bool`
  - `unhealthy_subscriptions(max_stale=15.0) -> List[int]`
- **Subscription-level auto-recovery** (`subscribe.py`): `_auto_recover_subscriptions()` GC
  sweep called from `_dispatch_loop` every ~200 iterations (~1s). Dead subscriptions are
  silently unsubscribed and re-registered individually.
- **Data validation** (`subscribe.py`): `_value_is_plausible()` filters NaN, inf, and values
  exceeding ±1e15 on the dispatch path before they reach the callback. Invalid values are
  silently dropped (warning logged).
- **Throttled batch restore** (`subscribe.py`): `_restore_subscriptions()` now restores in
  batches of 10 subscriptions with 5ms delay between batches, avoiding the ~400 simultaneous
  SimConnect calls that caused MSFS frame drops (180→30).

### Changed

- **Dispatch zombie hardening** (`client.py`): `start_background_dispatch()` now refuses to
  start a new dispatch thread while the old thread is still alive (`dispatch_zombie`). Raises
  `RuntimeError` instead of silently creating a second thread that would corrupt SimConnect
  state (dual-thread CallDispatch was the root cause of data loss and corruption).
- `unsubscribe()` now cleans up per-subscription health tracking state.
- Module-level constants added for health/restore tuning:
  `_SUB_HEALTH_MAX_STALE`, `_SUB_HEALTH_GC_INTERVAL`, `_SUB_RESTORE_BATCH_SIZE`,
  `_SUB_RESTORE_BATCH_DELAY`, `_SUB_VALUE_MAX_PLAUSIBLE`.

### Fixed

- **Root cause of "data getting stuck"**: dual-thread CallDispatch caused by zombie detection
  starting a new dispatch thread while the old one was still alive. Now raises instead,
  forcing the caller to complete a full reconnect.
- **Root cause of "values jumping to absurd numbers"**: NaN, inf, and extreme values from
  SimConnect now filtered at the subscription dispatch level.
- **Root cause of "MSFS frame drop on reconnect"**: batch restore now throttled to 10
  subscriptions per batch with 5ms delay.
- **Root cause of "micro-stutter"**: Zombie detection no longer silently creates a competing
  dispatch thread; the auto-recovery GC runs lightweight single-subscription repairs instead
  of full teardown/restore cycles.

### Changed

- **OPEN → SimStart 去重重挂** (`client.py`): OPEN 立即 `_restore_subscriptions()`（满足订阅
  延迟注册契约）+ 跟踪 `_open_restored_at`。SimStart 定时恢复时检查该时间戳，8s 内跳过重复
  恢复。
- **`ensure_background_dispatch` 线程安全** (`client.py`): 加 `self._lock` 保护，消除
  双线程同时启动 dispatch 的竞态条件。
- **zombie force 绕过** (`client.py`): `start_background_dispatch` 检测到 zombie 时若
  `_dispatch_abandoned` 为 True（由 `stop_background_dispatch(force=True)` 设置），
  跳过等待直接启动新线程，恢复 `restart_background_dispatch(force=True)` 的原有语义。
- **测试版本号** (`tests/test_simconnect_native.py`): 更新为 `"0.7.0"`。

## [0.6.4] - 2026-06-17

### Fixed

- `parsing.py`: Python 3 `c_char` bytes comparison; safe STRINGV vs C-string detection (incl. len>=32)
- Parse failures in `get`/`get_many` and subscription dispatch now log warnings with field/req_id
- Auto-reconnect logs success only after OPEN received; reset reconnect backoff on success

### Changed

- Complete `__all__` exports for imported SimConnect constants

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
