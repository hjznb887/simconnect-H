# simconnect-H

**原生 ctypes SimConnect 库 — 零外部依赖，直接加载 SimConnect.dll 与 Microsoft Flight Simulator 通讯。**

## 特性

- **零依赖** — 仅 `ctypes` 标准库，纯 Python、可 PyInstaller 打包
- **MIT 许可** — 无 AGPL 污染，可闭源商用
- **线程安全** — dispatch 回调加锁保护
- **一键连接** — `connect()` 自动加载 DLL、扫描 `config_index`、等待 OPEN、启动后台 dispatch
- **高层 API** — `get()` / `set()` / `subscribe()` 开箱即用
- **智能搜索** — 自动定位 SimConnect.dll（游戏目录优先）

## 安装

```bash
pip install .

# 开发模式（改代码立即生效，推荐）
pip install -e .
```

也可直接复制 `simconnect_native/` 到项目目录。

### SimConnect.dll

需要 MSFS SDK 可再发行版 `SimConnect.dll`（64 位）。查找顺序：

1. 环境变量 `SIMCONNECT_DLL`
2. 便携 exe 同目录（及 `lib\SimConnect.dll`）
3. **MSFS 游戏安装目录**（Steam / Microsoft Store，与运行中模拟器版本一致）
4. 包内置 `simconnect_native/lib/SimConnect.dll`
5. MSFS SDK 安装路径

复制 SDK DLL 到包内：

```powershell
scripts\copy_simconnect_dll.ps1
```

手动指定：

```python
sc = SimConnect()
sc.load_dll(r"D:\MSFS SDK\SimConnect SDK\lib\SimConnect.dll")
```

## 快速入门

MSFS 已启动并进入飞行（未暂停）后：

```python
from simconnect_native import SimConnect

with SimConnect() as sc:
    sc.connect("MyApp")  # 加载 DLL + 连接 + 后台 dispatch

    alt = sc.get("PLANE ALTITUDE", "feet", timeout=2.0)
    print(f"高度: {alt:.1f} ft")

    sc.subscribe("AIRSPEED INDICATED", "knots", lambda v: print(f"IAS: {v:.0f}"))
    import time
    time.sleep(5)
```

### 命令行验证

```powershell
cd D:\simconnect-H
pip install -e .          # 首次
python examples\diagnose_read.py   # 完整诊断
python examples\read_write.py      # 读写示例
```

诊断通过时会输出 `读数链路正常` 及实际高度值。

## 底层 API 示例

需要手动控制 dispatch 时：

```python
import ctypes
from simconnect_native import (
    SimConnect,
    SIMCONNECT_DATATYPE_FLOAT64,
    SIMCONNECT_SIMOBJECT_TYPE_USER,
    SIMCONNECT_RECV_ID_OPEN,
    SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE,
)

with SimConnect() as sc:
    sc.connect("MyApp", start_dispatch=False)

    sc.add_to_data_definition(
        1, b"PLANE ALTITUDE", b"feet", SIMCONNECT_DATATYPE_FLOAT64
    )

    def on_dispatch(p_data, _cb, _ctx):
        if p_data.contents.dwID == SIMCONNECT_RECV_ID_OPEN:
            print("已连接")
        elif p_data.contents.dwID == SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE:
            _req, val = sc.read_double(p_data)
            print(f"高度: {val}")

    sc.set_dispatch_cb(on_dispatch)
    sc.start_background_dispatch()
    sc.request_data_on_simobject_type(1, 1, 0, SIMCONNECT_SIMOBJECT_TYPE_USER)

    import time
    time.sleep(5)
```

## API 一览

### `SimConnect` 类

| 方法 | 说明 |
| ------ | ------ |
| `connect(app_name, ...)` | 一键连接（推荐） |
| `load_dll(path=None)` | 加载 SimConnect.dll |
| `open(app_name, config_index=0, ...)` | 底层连接 |
| `close()` | 断开连接 |
| `get(var, unit, timeout=0.1, ...)` | 同步读取 SimVar |
| `set(var, value, unit, ...)` | 写入 SimVar |
| `subscribe(var, unit, callback, ...)` | 订阅 SimVar 更新 |
| `subscribe_many(fields, callback, ...)` | 一次订阅多个 SimVar |
| `unsubscribe(sub_id)` | 取消订阅 |
| `trigger(event_name, ...)` | 触发 MSFS 事件 |
| `add_to_data_definition(id, name, unit, datatype=FLOAT64, ...)` | 注册 SimVar |
| `request_data_on_simobject_type(...)` | 按类型请求数据 |
| `request_data_on_simobject(...)` | 按 objectID 请求数据 |
| `dispatch()` | 处理一次消息队列 |
| `start_background_dispatch()` | 启动后台 dispatch（含自动重连） |
| `read_double(pData)` / `read_data(pData, datatype)` | 从回调解析数据 |

### 属性

| 属性 | 说明 |
| ------ | ------ |
| `handle` | SimConnect 句柄 |
| `is_open` | 是否已连接 |
| `on_connect` / `on_disconnect` | 连接状态回调 |

### 模块工具

| 函数 | 说明 |
| ------ | ------ |
| `find_simconnect_dll()` | 搜索 SimConnect.dll |
| `describe_simconnect_dll_path(path)` | 说明 DLL 来源 |
| `__version__` | 当前版本 |

## 迁移说明

### v0.5.0 — `SIMCONNECT_DATATYPE` 与 MSFS SDK 对齐

旧版错误沿用了 FSX 枚举值（`FLOAT64=0`）。MSFS SDK 正确值为：

| 常量 | 值 |
| ------ | --- |
| `SIMCONNECT_DATATYPE_INVALID` | 0 |
| `SIMCONNECT_DATATYPE_INT32` | 1 |
| `SIMCONNECT_DATATYPE_INT64` | 2 |
| `SIMCONNECT_DATATYPE_FLOAT32` | 3 |
| `SIMCONNECT_DATATYPE_FLOAT64` | 4 |
| `SIMCONNECT_DATATYPE_STRINGV` | 11 |

`get()` / `set()` / `subscribe()` 默认已使用 `FLOAT64(4)`，一般无需改代码。若曾手动传入 `datatype=0` 期望 float64，请改为 `4` 或 `SIMCONNECT_DATATYPE_FLOAT64`。

### v0.4.0 — 消息头与 `SIMCONNECT_RECV_ID_*`

`SIMCONNECT_RECV` 字段顺序与 MSFS SDK 一致（`dwSize, dwVersion, dwID`）。请使用本库导出的常量，勿硬编码旧值。

## 许可证

MIT License
