# simconnect-H

**面向 MSFS 的原生 Python SimConnect 库** — 仅用标准库 `ctypes` 加载 `SimConnect.dll`，零 pip 依赖，可 PyInstaller 打包、可闭源商用（MIT）。

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows-lightgrey.svg)]()

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
- **线程安全** — dispatch 与订阅路由加锁；并发 `get()` 串行隔离

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

### 命令行自检

```powershell
pip install -e .
python examples\diagnose_read.py   # 数值 SimVar，应输出「读数链路正常」
python examples\read_strings.py    # 字符串 SimVar（TITLE / ATC TYPE）
python examples\read_write.py
```

---

## 推荐用法：高频 + 多变量

**读**：用 `subscribe_many` 推送，不要循环 `get()`。  
**写**：用 `set()` / `trigger()`，发完即返。

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
    sc.connect("Telemetry")

    sc.subscribe_many(
        FIELDS,
        lambda d: state.update(d),
        period=SIMCONNECT_PERIOD_SIM_FRAME,
    )

    while running:
        # 读 state，写控制
        sc.set("GENERAL ENG THROTTLE LEVER POSITION:1", 0.75, "percent")
        time.sleep(0.02)  # 20ms 由你的业务决定，库按 sim 帧推送
```

| 场景 | 推荐 API |
|------|----------|
| 偶尔读一次 | `get()` |
| 20–50 Hz、几十个变量 | `subscribe_many()` |
| 写 SimVar / 发事件 | `set()` / `trigger()` |
| 字符串 SimVar（TITLE 等） | `get_string()` / `subscribe_string()` |
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

**注意：** `subscribe_many` 目前仅支持数值类型批量打包；字符串 SimVar 请单独 `subscribe_string()`。

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
| `connect(app_name, ...)` | **推荐** 一键连接 |
| `load_dll(path=None)` | 加载 DLL |
| `open(...)` / `close()` | 底层连接 / 断开 |
| `start_background_dispatch()` | 后台 pump（含自动重连） |
| `ensure_background_dispatch()` | 未运行时启动 dispatch（幂等） |

### 数据读写

| 方法 | 说明 |
|------|------|
| `get(var, unit, timeout=0.1)` | 同步读（单次，勿高频轮询） |
| `get_string(var, timeout=1.0)` | 同步读字符串 SimVar |
| `set(var, value, unit)` | 写 SimVar |
| `subscribe(var, unit, callback, period=SIM_FRAME)` | 单变量订阅 |
| `subscribe_string(var, callback, period=SIM_FRAME)` | 字符串 SimVar 订阅 |
| `subscribe_many(fields, callback, period=SIM_FRAME)` | **多变量批量订阅（数值）** |
| `unsubscribe(sub_id)` | 取消订阅 |
| `trigger(event_name, ...)` | 触发 MSFS 事件 |
| `ensure_background_dispatch()` | 幂等启动后台 dispatch |

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
