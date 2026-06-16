# simconnect-H 贡献与架构原则

> **SimConnect 只能有一个消息泵，结构体必须跟 SDK 一致；改进应集中在串行化 IO 和可靠停/启 dispatch，而不是改 packing 或加第二个 pump。**

## 设计约束

| 做 | 不做 |
|---|---|
| 单 pump 线程（后台 `CallDispatch`） | 双 pump「并发优化」（前台 `get()` + 后台同时 dispatch） |
| **写入队列**：`set`/`trigger` 入队，dispatch 线程 drain | 多线程无锁同时碰 `hSimConnect` |
| `_io_lock` 串行化 DLL 调用 | 改 ctypes 结构体 `_pack_`（必须与 MSFS SDK 布局一致） |
| `stop_background_dispatch() -> bool` + zombie/`force` 恢复 | 假设 `CallDispatch` 可在 Python 侧被中断 |

## 写入队列（v0.5.5+）

后台 dispatch 运行时，`set()` / `trigger()` / `set_string()` **自动入队**，在两次 `CallDispatch` 之间由 pump 线程执行：

```python
sc.connect("MyApp")  # 默认 start dispatch
sc.subscribe_many(FIELDS, on_data)

# 无需 stop dispatch
sc.set("AMBIENT TEMPERATURE", 18, "Celsius")
sc.trigger("WIND_DIRECTION_SET", 270)

# 异步
fut = sc.submit_set("AMBIENT TEMPERATURE", 18, "Celsius")
fut.wait(timeout=2.0)
sc.flush_write_queue()
```

`get()` 在 dispatch 已运行时不主动 pump，只等待 `_pending_get` 事件。

## 推荐连接顺序（多路订阅）

```python
sc.connect("MyApp", start_dispatch=False)
sc.subscribe_many(FIELDS, on_data)
sc.start_background_dispatch()
```

## 健康检查

```python
sc.dispatch_thread_alive
sc.dispatch_zombie
sc.is_dataflow_healthy(max_stale=2.0)
sc.restart_dispatch(force=True)
```

## 字符串 SimVar（MSFS）

TITLE / ATC TYPE 等为 **null-terminated C 字符串**（读）；写用 `set_string()`（STRINGV 长度前缀）。

## 版本对照

| 能力 | 版本 |
|------|------|
| STRINGV / C 字符串读修复 | v0.5.3 |
| `_io_lock`、dispatch 健康 API、`with_paused_dispatch` | v0.5.4 |
| **写入队列** `submit_set` / 自动入队 | v0.5.5–v0.5.6 |
| 天气 API / 生命周期钩子 / batch_subscribe | v0.5.7 |
| `get_many()` 批量同步读 | v0.6.0 |
| `subscribe_many` 混合字符串 | v0.6.1 |
