# simconnect-H

**原生 ctypes SimConnect 库 — 零外部依赖，直接加载 SimConnect.dll 与 Microsoft Flight Simulator 通讯。**

## 特性

- 🚫 **零 Python 依赖** — 仅使用 Python 标准库 `ctypes`，无任何第三方包
- 🔓 **无 AGPL 污染** — 不依赖 PySimConnect，MIT 许可证
- 🎯 **完全控制** — 手动定义所有 `argtypes`，无 Enum 类型漏洞
- 🪶 **轻量** — 单个文件，即插即用
- 🏗️ **可打包** — 支持 `pip install` 和 PyInstaller 打包

## 安装

```bash
# 从源码安装
pip install .

# 或直接复制 simconnect_native/ 到项目目录
```

需要 `SimConnect.dll`（微软模拟飞行 SDK 可再发行组件），程序会自动在以下位置查找：

1. 当前目录
2. `site-packages/SimConnect/`（PySimConnect 安装路径）
3. 系统 PATH

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

sc = SimConnect()
sc.load_dll()
sc.open(b"MyApp")

# 注册数据定义
sc.add_to_data_definition(1, b"PLANE ALTITUDE", b"Feet")
sc.add_to_data_definition(2, b"INDICATED ALTITUDE", b"Feet")

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

    elif dwID == SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE:
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
from ctypes import c_double, cast, c_void_p, sizeof as c_sizeof
arr = (c_double * 1)(1000.0)
ptr = cast(arr, c_void_p)
sc.set_data_on_simobject(1, data_ptr=ptr)

# 发送事件
sc.map_client_event_to_sim_event(100, b"KEY_TOGGLE")
sc.transmit_client_event(0, 100, 0)

sc.close()
```

## API 一览

### `SimConnect` 类

| 方法 | 说明 |
|------|------|
| `load_dll(path=None)` | 加载 SimConnect.dll |
| `open(app_name, ...)` | 连接 MSFS |
| `close()` | 断开连接 |
| `add_to_data_definition(id, name, unit, ...)` | 注册 SimVar |
| `clear_data_definition(id)` | 清除定义 |
| `request_data_on_simobject_type(req_id, def_id, ...)` | 请求数据 |
| `set_data_on_simobject(def_id, ...)` | 写入数据 |
| `map_client_event_to_sim_event(ev_id, name)` | 映射事件 |
| `transmit_client_event(obj_id, ev_id, data, ...)` | 发送事件 |
| `subscribe_to_system_event(id, name)` | 订阅系统事件 |
| `dispatch()` | 处理一次消息队列 |
| `set_dispatch_cb(callback)` | 设置 dispatch 回调 |
| `call_dispatch(callback)` | 设置并触发 dispatch |
| `read_double(pData)` | 从回调中解析 float64 值 |

### 属性

| 属性 | 说明 |
|------|------|
| `handle` | SimConnect 句柄（HANDLE） |
| `dll` | 已加载的 WinDLL 对象 |
| `is_open` | 是否已连接 |

## 许可证

MIT License
