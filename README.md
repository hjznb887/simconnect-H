# simconnect-H

**原生 ctypes SimConnect 库 — 零外部依赖，直接加载 SimConnect.dll 与 Microsoft Flight Simulator 通讯。**

## 特性

- 🚫 **零依赖** — 仅 `ctypes` 标准库，纯 Python、可 PyInstaller 打包
- 🔓 **MIT 许可** — 无 AGPL 污染，可闭源商用
- 🪶 **单文件** — 即插即用，源码仅 ~800 行
- 🔒 **线程安全** — dispatch 回调加锁保护
- 📦 **上下文管理器** — 支持 `with sc:` 自动断开
- 🔍 **智能搜索** — 自动定位 SimConnect.dll

## 安装

```bash
# 从源码安装
pip install .

# 或直接复制 simconnect_native/ 到项目目录
```

需要 `SimConnect.dll`（微软模拟飞行 SDK 可再发行组件），程序会自动在以下位置查找：

1. MSFS SDK 安装目录（`Program Files (x86)/Microsoft SDKs/FlightSimulator/`）
2. 本文件同目录
3. 当前工作目录
4. `site-packages/SimConnect/`（PySimConnect 安装路径）
5. 系统 PATH

也可以手动指定路径：

```python
sc = SimConnect()
sc.load_dll(r"C:\Path\To\SimConnect.dll")
```

## 快速入门

```python
from simconnect_native import (
    SimConnect,
    SIMCONNECT_SIMOBJECT_TYPE_USER,
    SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE,
    SIMCONNECT_RECV_ID_OPEN,
    SIMCONNECT_RECV_ID_EXCEPTION,
    FULL_SIMOBJECT_DATA, EXCEPTION_MSG, EXCEPTION_NAMES,
)

# 支持 with 语句，自动 close
with SimConnect() as sc:
    sc.load_dll()
    sc.open(b"MyApp")

    # 注册数据定义
    sc.add_to_data_definition(1, b"PLANE ALTITUDE", b"Feet")

    # 设置 dispatch 回调
    def on_dispatch(pData, cbData, pContext):
        try:
            dwID = pData.contents.dwID
        except Exception:
            return

        if dwID == SIMCONNECT_RECV_ID_OPEN:
            print("✓ 已连接到 MSFS")

        elif dwID == SIMCONNECT_RECV_ID_EXCEPTION:
            exc = ctypes.cast(pData, ctypes.POINTER(EXCEPTION_MSG)).contents
            name = EXCEPTION_NAMES.get(exc.dwException, f"UNKNOWN({exc.dwException})")
            print(f"⚠ 异常: {name}")

        elif dwID in (
            SIMCONNECT_RECV_ID_SIMOBJECT_DATA,
            SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE,
        ):
            req_id, val = sc.read_double(pData)
            print(f"📊 req={req_id} value={val}")

    sc.set_dispatch_cb(on_dispatch)

    # 请求数据
    sc.request_data_on_simobject_type(1, 1, 0, SIMCONNECT_SIMOBJECT_TYPE_USER)

    # 轮询
    import time
    for _ in range(100):
        sc.dispatch()
        time.sleep(0.01)

    # 写入数据
    from ctypes import c_double, cast, c_void_p
    arr = (c_double * 1)(1000.0)
    ptr = cast(arr, c_void_p)
    sc.set_data_on_simobject(1, data_ptr=ptr)

    # 发送事件
    sc.map_client_event_to_sim_event(100, b"KEY_TOGGLE")
    sc.transmit_client_event(0, 100, 0)

# with 块结束自动断开
```

> **v0.2.0 迁移说明**：`FULL_SIMOBJECT_DATA` 已精简为头部元数据结构体（`SIMOBJECT_DATA_HEADER`），不再包含预分配的 `dwData` 数组。
> 所有数据读取请改用 `SimConnect.read_data(pData, datatype)` 或 `sc.read_double(pData)`，内部使用指针偏移零拷贝读取。
> 向后兼容：`FULL_SIMOBJECT_DATA` 名称仍可作为 `SIMOBJECT_DATA_HEADER` 的别名导入。

> **v0.4.0 迁移说明**：`SIMCONNECT_RECV` 字段顺序与 `SIMCONNECT_RECV_ID_*` 常量已与 MSFS SDK 对齐（`dwSize, dwVersion, dwID`；`SIMOBJECT_DATA=8`）。
> 若代码中硬编码了旧值（如 `14`）或依赖错误的 16 字节头部，请改用本库导出的常量。

## API 一览

### `SimConnect` 类

| 方法 | 说明 |
| ------ | ------ |
| `load_dll(path=None)` | 加载 SimConnect.dll |
| `open(app_name, ...)` | 连接 MSFS |
| `close()` | 断开连接 |
| `add_to_data_definition(id, name, unit, ...)` | 注册 SimVar |
| `clear_data_definition(id)` | 清除定义 |
| `request_data_on_simobject_type(req_id, def_id, ...)` | 请求数据 |
| `request_data_on_simobject(req_id, def_id, ...)` | 请求持续数据更新 |
| `add_and_request(req_id, def_id, name, unit, ...)` | 注册+请求一步完成 |
| `set_data_on_simobject(def_id, *, object_id, flags, ...)` | 写入数据 |
| `write_double(def_id, value)` | 快捷写入 double 值 |
| `map_client_event_to_sim_event(ev_id, name)` | 映射事件 |
| `transmit_client_event(obj_id, ev_id, data, ...)` | 发送事件 |
| `subscribe_to_system_event(id, name)` | 订阅系统事件 |
| `dispatch()` | 处理一次消息队列 |
| `set_dispatch_cb(callback)` | 设置 dispatch 回调 |
| `call_dispatch(callback)` | 设置并触发 dispatch |
| `read_double(pData)` | 从回调中解析 float64 值 |
| `read_data(pData, datatype=0)` | 从回调指针按类型读取数据（静态方法，零拷贝） |
| `parse_exception(pData)` | 解析异常消息，返回 (名称, sendID, index)（静态方法） |
| `start_background_dispatch(callback=None)` | 启动后台 dispatch 线程（含自动重连） |
| `stop_background_dispatch()` | 停止后台 dispatch 线程 |
| `subscribe(var_name, unit, callback, period=3, datatype=0)` | 高层 SimVar 订阅（自动管理定义+请求+dispatch 分发） |
| `get_last_sent_packet_id()` | 获取最后发送的数据包 ID |
| `event_data_float(value)` | float → DWORD 位转换（静态方法） |

### 属性

| 属性 | 说明 |
| ------ | ------ |
| `handle` | SimConnect 句柄（HANDLE） |
| `dll` | 已加载的 WinDLL 对象 |
| `is_open` | 是否已连接 |

### 模块级工具

| 函数 | 说明 |
| ------ | ------ |
| `find_simconnect_dll()` | 自动搜索 SimConnect.dll 路径 |
| `read_data_value(pData, datatype=0)` | 从 dispatch 回调中读取指定类型数据 |
| `__version__` | 当前库版本 `"0.4.0"` |

## 许可证

MIT License
