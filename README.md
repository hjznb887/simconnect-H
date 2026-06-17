# simconnect-H

**中文** · [English](docs/en/README.md)

**Native Python SimConnect for MSFS** — zero pip dependencies, `ctypes` only, PyInstaller-friendly (MIT).

**面向 MSFS 的原生 Python SimConnect 库** — 仅用标准库 `ctypes` 加载 `SimConnect.dll`，零 pip 依赖，可 PyInstaller 打包、可闭源商用（MIT）。

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)]()
[![Tests](https://github.com/hjznb887/simconnect-H/actions/workflows/test.yml/badge.svg)](https://github.com/hjznb887/simconnect-H/actions/workflows/test.yml)

**文档：** [Cookbook](docs/cookbook.md) · [架构原则](docs/simconnect-h-contribution.md)

### English quick start

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

- Read / write SimVars, batch `subscribe_many`, trigger events
- Auto-reconnect, write queue, single message pump (thread-safe)
- CLI: `simconnect-h get / set / watch / trigger / doctor / search`
- Asyncio: `from simconnect_native.asyncio import AsyncSimConnect`

```python
from simconnect_native.asyncio import AsyncSimConnect

async with AsyncSimConnect.session("MyApp") as asc:
    alt = await asc.get("PLANE ALTITUDE", "feet")
    async for data in asc.subscribe_stream({"alt": ("PLANE ALTITUDE", "feet")}):
        print(data)
```

---


## 为什么选它

| | simconnect-H | 典型 FSX 时代封装 |
|---|:---:|:---:|
| 依赖 | 仅 ctypes | 第三方包 / 旧枚举 |
| MSFS `DATATYPE` | 与 SDK 一致（`FLOAT64=4`） | 常错成 `0` |
| 连接 | `connect()` 一键搞定 | 需自己试 config_index |
| 高频数据 | `subscribe_many` 批量推送 | 多靠轮询 `get()` |

---

## 特性

- **零依赖** — 不拉 PyPI 运行时包，复制目录或 `pip install -e .` 即可
- **一键连接** — 自动找 DLL、扫描 `config_index` 0–7、等待 OPEN、启动后台 dispatch
- **三层 API** — `get` / `set` / `subscribe` 开箱即用；底层 ctypes 接口完整保留
- **批量订阅** — `subscribe_many` 一次定义几十个 SimVar，适合 20–50 Hz 遥测
- **健壮性** — HRESULT 严格检查、自动清理、`SimConnectError` 明确报错
- **线程安全** — 全局 `_io_lock` 串行化 DLL 调用；后台 dispatch 运行时 `get()` 不再双 pump

---

## 安装

```bash
git clone https://github.com/hjznb887/simconnect-H.git
cd simconnect-H
pip install -e .
```

或直接复制 [`simconnect_native/`](simconnect_native/) 到你的项目。

### SimConnect.dll 从哪来

需要 **64 位** MSFS SDK 可再发行版 `SimConnect.dll`。查找顺序：

1. 环境变量 `SIMCONNECT_DLL`
2. 便携 exe 同目录 / `lib\SimConnect.dll`
3. **MSFS 游戏目录**（Steam / Microsoft Store，与运行中模拟器同版本）
4. 包内 `simconnect_native/lib/SimConnect.dll`
5. MSFS SDK 安装路径

```powershell
# 可选：把 SDK DLL 复制进包内
scripts\copy_simconnect_dll.ps1
```

---

## 30 秒上手

MSFS 已启动、进入飞行、**未暂停**：

```python
from simconnect_native import SimConnect

with SimConnect() as sc:
    sc.connect("MyApp")

    alt = sc.get("PLANE ALTITUDE", "feet", timeout=2.0)
    print(f"高度: {alt:.1f} ft")

    sc.subscribe("AIRSPEED INDICATED", "knots", lambda v: print(f"IAS: {v:.0f}"))

    import time
    time.sleep(5)
```

### 命令行

```powershell
pip install -e .
simconnect-h ping                              # 连通性 + 读高度
simconnect-h get "PLANE ALTITUDE" feet
simconnect-h watch "AIRSPEED INDICATED" knots --seconds 10
simconnect-h search altitude                   # 搜常用 SimVar
python examples\diagnose_read.py               # 详细诊断
python examples\stress_subscribe.py            # 40+ 路订阅 + 并发写压测
```

---

## 推荐用法：高频 + 多变量

**读**：用 `subscribe_many` 推送，不要循环 `get()`。  
**写**：`set()` / `trigger()` 在后台 dispatch 运行时 **自动走写入队列**，由 pump 线程串行执行，无需再 `stop_background_dispatch()`。

```python
# 订阅跑着也能写（推荐）
sc.set("GENERAL ENG THROTTLE LEVER POSITION:1", 0.75, "percent")
sc.trigger("AP_MASTER")

# 异步 + 可选 flush
fut = sc.submit_set("GENERAL ENG THROTTLE LEVER POSITION:1", 0.75, "percent")
fut.wait(timeout=2.0)
```

```python
from simconnect_native import SimConnect, SIMCONNECT_PERIOD_SIM_FRAME

FIELDS = {
    "alt": ("PLANE ALTITUDE", "feet"),
    "ias": ("AIRSPEED INDICATED", "knots"),
    "hdg": ("PLANE HEADING DEGREES TRUE", "degrees"),
    # … 继续加到几十个
}

state = {}

with SimConnect() as sc:
    sc.connect("Telemetry", start_dispatch=False)
    with sc.batch_subscribe():
        sc.subscribe_many(FIELDS, lambda d: state.update(d), period=SIMCONNECT_PERIOD_SIM_FRAME)
        sc.subscribe_string("TITLE", on_title, immediate_first=True)
    # 退出 batch_subscribe 后自动 ensure_background_dispatch()

    while running:
        # 读 state，写控制
        sc.set("GENERAL ENG THROTTLE LEVER POSITION:1", 0.75, "percent")
        time.sleep(0.02)  # 20ms 由你的业务决定，库按 sim 帧推送
```

| 场景 | 推荐 API |
|------|----------|
| 偶尔读一次 | `get()` / `get_many()` |
| 20–50 Hz、几十个变量 | `subscribe_many()` |
| 写 SimVar / 发事件 | `set()` / `trigger()` |
| 字符串 SimVar（TITLE 等） | `get_string()` / `subscribe_string()` 或混在 `subscribe_many` |
| 完全自控协议 | 底层 `add_to_data_definition` + dispatch |

---

## 字符串 SimVar（TITLE / ATC TYPE 等）

MSFS 对字符串 SimVar 在 `dwData` 处返回 **null-terminated C 字符串**（不是 `"String"` 单位，SDK 要求 **unit=NULL**）。库已自动处理：

```python
from simconnect_native import SimConnect

with SimConnect() as sc:
    sc.connect("MyApp")

    title = sc.get_string("TITLE", timeout=3.0)
    print(title)  # 例如 "VL3 Asobo"

    sc.subscribe_string("ATC TYPE", lambda s: print(f"type: {s}"))
    sc.ensure_background_dispatch()  # connect() 已启动时可省略

    import time
    time.sleep(5)
```

也可显式指定 `datatype=SIMCONNECT_DATATYPE_STRINGV`，`unit` 传 `""` 即可（内部会转为 NULL）。

**注意：** `subscribe_many` 支持数值与字符串字段混合；回调收到合并后的 `{key: value}` dict。

---

## 架构一览

```
SimConnect.connect()
    ├── load_dll()          搜索 SimConnect.dll
    ├── open()              SimConnect_Open + SimStart 订阅
    └── background dispatch 后台线程 pump 消息
            ├── OPEN / QUIT / SimStart  → 重连与恢复订阅
            ├── subscribe 回调          → SimVar 推送
            └── get() 同步读            → 一次性 Request + Event
```

资源管理：推荐 `with SimConnect() as sc:` 或显式 `close()`；析构时会兜底释放句柄。

---

## API 速查

### 连接与生命周期

| 方法 | 说明 |
|------|------|
| `connect(app_name, ...)` / `SimConnect.session(app_name)` | **推荐** 一键连接 |
| `load_dll(path=None)` | 加载 DLL |
| `open(...)` / `close()` | 底层连接 / 断开 |
| `start_background_dispatch()` | 后台 pump（含自动重连） |
| `stop_background_dispatch(timeout=5.0, force=False) -> bool` | 停止 pump；返回是否真正退出（`False` = zombie） |
| `restart_background_dispatch(force=False)` / `restart_dispatch(force=False)` | 重启 pump；`restart_dispatch` 还会 `_restore_subscriptions()`（**30s 冷却**，`force=True` 跳过） |
| `mark_dataflow_quiet(seconds=8)` | 换机/新航班后短暂窗口内 `is_dataflow_healthy()` 返回 True |
| `_schedule_restore_subscriptions`（内部） | OPEN / SimStart / ASSIGNED_OBJECT_ID **2s 内合并**为一次 restore |
| `ensure_background_dispatch()` | 未运行时启动 dispatch（幂等） |
| `with_paused_dispatch(...)` | 上下文管理器：暂停 pump，finally 可选恢复 |
| `dispatch_thread_alive` / `dispatch_zombie` | 线程是否存活 / flag 已停但线程仍卡住 |
| `is_dataflow_healthy(max_stale=2.0)` | dispatch 在跑且近期有订阅回调 |

### 后台 dispatch 语义

1. **批量订阅**：`connect(..., start_dispatch=False)` → 多次 `subscribe()` / `subscribe_many()` → 再一次 `start_background_dispatch()`（多路订阅依赖此顺序）。
2. **`stop_background_dispatch()` 是 best-effort**：`CallDispatch` 可能长时间阻塞，超时内未退出时返回 `False` 且 **保留** `_dispatch_thread` 引用（避免状态与事实不一致）。上层可用 `force=True` 或 `restart_dispatch(force=True)` 标记 abandoned 并起新 pump 线程。
3. **不要双 pump**：后台 dispatch 运行时，`get()` 只等待事件、不再主动 `dispatch()`；需要同步读写与 pump 互斥时用 `with_paused_dispatch()`。
4. **健康检查**：勿仅用 `_dispatch_running` 判断；用 `is_dataflow_healthy()` 或 `dispatch_zombie`。

架构原则见 [`docs/simconnect-h-contribution.md`](docs/simconnect-h-contribution.md)。

### 数据读写

| 方法 | 说明 |
|------|------|
| `get(var, unit, timeout=0.1)` | 同步读（单次，勿高频轮询） |
| `get_many(fields, timeout=0.5)` | **批量同步读** `{key: value}` |
| `get_string(var, timeout=1.0)` | 同步读字符串 SimVar |
| `set(var, value, unit)` | 写 SimVar（dispatch 在跑时自动入队） |
| `set_string(var, value)` | 写字符串 SimVar |
| `submit_set(...)` / `submit_trigger(...)` | 异步入队，返回 `WriteFuture` |
| `submit(callable)` | 自定义写入操作入队 |
| `flush_write_queue(timeout=5.0)` | 等待队列排空 |
| `write_queue_depth` / `write_queue_enabled` | 队列深度 / 是否自动入队 |
| `subscribe(var, unit, callback, period=SIM_FRAME)` | 单变量订阅 |
| `subscribe_string(var, callback, period=SIM_FRAME)` | 字符串 SimVar 订阅 |
| `subscribe_many(fields, callback, period=SIM_FRAME)` | **多变量批量订阅（数值+字符串可混合）** |
| `unsubscribe(sub_id)` | 取消订阅 |
| `trigger(event_name, ...)` | 触发 MSFS 事件 |
| `subscribe_system_event(name, callback)` | 系统事件 Pause / SimStop 等 |

### 天气（Legacy）

MSFS 2020 下 SimConnect 天气控制**效果不稳定**，不再作为推荐能力。以下 API 保留兼容，**无效果保证**：

| 方法 | 说明 |
|------|------|
| `weather_set_mode_custom()` | 切换自定义天气模式 |
| `weather_set_observation(metar, seconds=0)` | 设置 METAR |
| `weather_apply_metar(metar)` | METAR + ModeCustom |
| `weather_set_ambient(...)` | 环境滑块类 SimVar |

### 生命周期钩子

| 成员 | 说明 |
|------|------|
| `on_sim_start` | OPEN / SimStart / ASSIGNED_OBJECT_ID 时调用 |
| `on_aircraft_changed` | 配合 `enable_aircraft_change_detection()` |
| `on_dispatch_zombie` | `stop_background_dispatch` 超时未退出时 |
| `batch_subscribe()` | 批量 subscribe 后自动 `ensure_background_dispatch()` |
| `enable_aircraft_change_detection()` | 订阅 TITLE，变化时触发 `on_aircraft_changed`（默认不拉首帧） |

`subscribe_string(..., immediate_first=True)` 可在后台拉首帧；默认 `False`，换机检测不再额外 `get_string`。

### `flush_write_queue` 注意

**不要在持有应用层锁时调用** `flush_write_queue()`——若 dispatch 回调也需要同一把锁，会死锁。改用 `WriteFuture.wait(timeout)` 或确保回调不抢锁。

### 常量（与 MSFS SDK 一致）

```python
from simconnect_native import (
    SIMCONNECT_DATATYPE_FLOAT64,   # 4
    SIMCONNECT_DATATYPE_STRINGV,   # 11 — TITLE 等字符串
    SIMCONNECT_PERIOD_SIM_FRAME,   # 3 — 每 sim 帧
    SIMCONNECT_PERIOD_VISUAL_FRAME,# 2 — 视觉帧
    SIMConnectError,
)
```

完整列表见 [`simconnect_native/constants.py`](simconnect_native/constants.py)。

---

## 底层示例

需要完全控制 dispatch 时：

```python
from simconnect_native import (
    SimConnect,
    SIMCONNECT_DATATYPE_FLOAT64,
    SIMCONNECT_SIMOBJECT_TYPE_USER,
    SIMCONNECT_RECV_ID_OPEN,
    SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE,
)

with SimConnect() as sc:
    sc.connect("MyApp", start_dispatch=False)
    sc.add_to_data_definition(1, b"PLANE ALTITUDE", b"feet", SIMCONNECT_DATATYPE_FLOAT64)

    def on_dispatch(p_data, _cb, _ctx):
        if p_data.contents.dwID == SIMCONNECT_RECV_ID_OPEN:
            print("OPEN")
        elif p_data.contents.dwID == SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE:
            _, val = sc.read_double(p_data)
            print(f"ALT: {val}")

    sc.set_dispatch_cb(on_dispatch)
    sc.start_background_dispatch()
    sc.request_data_on_simobject_type(1, 1, 0, SIMCONNECT_SIMOBJECT_TYPE_USER)
```

---

## 版本说明

### v0.6.3

- **文档同步**：[`docs/cookbook.md`](docs/cookbook.md) 补 FastAPI 节；contribution 版本表更新；英文文档链到架构原则
- **FastAPI 示例**：返回类型与 MSFS 启动顺序说明
- **CI**：optional `fastapi-smoke` job

### v0.6.2

- **英文文档** [`docs/en/`](docs/en/) — README、quickstart、API、cookbook、CLI
- **FastAPI 示例** [`examples/fastapi_telemetry.py`](examples/fastapi_telemetry.py) — `/snapshot` JSON + `/stream` SSE（可选依赖）

### v0.6.1

- **182+ SimVar / 69 事件** 目录；`simconnect-h search` 支持事件与推荐 unit
- **`subscribe_many` 混合数值+字符串**
- **`simconnect_native.asyncio`**：`AsyncSimConnect` + `subscribe_stream`
- 调试埋点移除；`get_many` 独立 ID 段等修复

### v0.6.0

- **`get_many()`** 批量同步读；**`DataField`** 字段辅助类型
- **`subscribe_system_event()`** — Pause / SimStop / AircraftLoaded 等
- **`SimConnect.session()`** 一键连接上下文
- **`simconnect-h` CLI** — get / set / watch / trigger / ping / doctor / search
- 天气 API 标为 Legacy；压测脚本改为 `stress_subscribe.py`（并发油门写）
- CI unittest、CHANGELOG、`py.typed`；Development Status → Beta

### v0.5.8

- **换机性能**：OPEN / SimStart / ASSIGNED_OBJECT_ID 触发的 `_restore_subscriptions` **2s 防抖合并**，避免 MSFS 突发掉帧
- **`mark_dataflow_quiet()`**：加载飞机后 8s 内 `is_dataflow_healthy()` 宽容，减少应用层误恢复
- **`restart_dispatch` 30s 冷却**（`force=True` 可跳过）
- **`enable_aircraft_change_detection` 默认 `immediate_first=False`**，不再后台拉 TITLE 首帧

### v0.5.7

- **天气 API**：`weather_set_mode_custom` / `weather_set_observation` / `weather_apply_metar` / `weather_set_ambient`
- **生命周期**：`on_sim_start` / `on_aircraft_changed` / `on_dispatch_zombie` / `batch_subscribe()` / `enable_aircraft_change_detection()`
- **`subscribe_string(..., immediate_first=True)`** 首帧后台 bootstrap
- **`flush_write_queue` 死锁警示**（文档 + docstring）
- 验收脚本 `examples/stress_subscribe_weather.py`；明确 `subscribe_many` 不支持字符串

### v0.5.6

- 写入队列 **enqueue 原子化**（`deque` + Condition，修复 pending 与入队竞态）
- `WriteFuture` 带操作 label，超时错误更可读
- `write_queue_enabled` 改为 property；`_data_ptr` 修正数值/字符串 buffer 传参

### v0.5.5

- **写入队列**：`submit_set` / `submit_trigger` / `submit`；`set()` / `trigger()` / `set_string()` 在后台 dispatch 运行时自动入队，由 pump 线程 drain
- **`WriteFuture`** + `flush_write_queue()` + `write_queue_depth`
- **`SimConnectWriteTimeoutError`**：同步等待写入超时
- stop dispatch 时会 **排空队列** 再退出线程

### v0.5.4

- **`stop_background_dispatch(timeout) -> bool`**：超时未退出时不置空线程引用；`force=True` 允许 zombie 场景再起 pump
- **`restart_background_dispatch` / `restart_dispatch` / `with_paused_dispatch`**
- **全局 `_io_lock`**：`dispatch` / `set` / `trigger` / 请求数据等 DLL 调用串行化，避免与后台 pump 抢句柄
- **`get()`**：后台 dispatch 运行时不主动 pump（消除双 pump 竞态）
- **可观测性**：`dispatch_thread_alive`、`dispatch_zombie`、`last_subscription_callback_monotonic`、`is_dataflow_healthy()`

### v0.5.3

- **修复字符串 SimVar 读取**：MSFS 对 TITLE/ATC TYPE 等返回 C 字符串，不再误按 STRINGV 长度前缀解析
- `AddToDataDefinition` 对字符串类型自动传 **unit=NULL**（与 SDK 一致）
- 新增 `get_string()` / `subscribe_string()` / `ensure_background_dispatch()`
- 导出 `SIMCONNECT_DATATYPE_STRING8` … `STRINGV` 全部字符串类型常量

### v0.5.2

- 修复 `connect(wait_open=True)` 未收到 OPEN 仍返回成功
- 修复 `subscribe` 回调内 `get()` 无法完成、并发 `get()` 串包
- 重连时重置 SimStart 订阅；用户 dispatch 回调异常不再静默
- HRESULT 严格化、常量补全、34 项单元测试

### v0.5.0

- **关键修复**：`SIMCONNECT_DATATYPE_FLOAT64 = 4`（MSFS SDK 正确值，非 FSX 的 `0`）
- 新增 `connect()`、`RequestDataOnSimObjectType` 读路径、游戏目录 DLL 优先

### 迁移提示

若旧代码手动传 `datatype=0` 期望 float64，请改为 `4` 或 `SIMCONNECT_DATATYPE_FLOAT64`。

---

## 开发与测试

```powershell
python -m unittest discover -s tests -v
```

---

## 许可证

[MIT License](LICENSE) — 可自由用于商业与闭源项目。
