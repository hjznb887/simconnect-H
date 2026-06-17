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

## FastAPI 桥接

通过 HTTP 暴露遥测，无需第二个 SimConnect pump。示例在应用 lifespan 内用 `AsyncSimConnect` 连接一次。

**端点：**

| 路由 | 说明 |
|------|------|
| `GET /health` | 存活检查（不访问 MSFS） |
| `GET /snapshot` | `get_many` JSON 快照 |
| `GET /stream` | `subscribe_stream` Server-Sent Events |

**运行：**

```powershell
pip install -e .
pip install -r examples/requirements-examples.txt
# MSFS 已启动、在飞行中：
uvicorn examples.fastapi_telemetry:app --host 127.0.0.1 --port 8765
```

浏览器访问 `http://127.0.0.1:8765/snapshot`，或：

```powershell
curl -N http://127.0.0.1:8765/stream
```

MSFS 未连接时 `/snapshot` 与 `/stream` 返回 **503** JSON 错误。MSFS 需在 **uvicorn 启动前** 已运行（lifespan 只 connect 一次；晚启动需重启服务）。

源码：[`examples/fastapi_telemetry.py`](../examples/fastapi_telemetry.py)。

## 健康检查

勿仅用 `_dispatch_running` 判断；用 `is_dataflow_healthy()`，或在 `stop_background_dispatch()` 后检查 `dispatch_zombie`。

## 不要双 pump

后台 dispatch 运行时 `get()` 不再主动 pump。需要与 pump 互斥的同步 I/O 时用 `with_paused_dispatch()`。
