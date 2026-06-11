# simconnect-H 贡献与架构原则

> **SimConnect 只能有一个消息泵，结构体必须跟 SDK 一致；改进应集中在串行化 IO 和可靠停/启 dispatch，而不是改 packing 或加第二个 pump。**

## 设计约束

| 做 | 不做 |
|---|---|
| 单 pump 线程（后台 `CallDispatch`） | 双 pump「并发优化」（前台 `get()` + 后台同时 dispatch） |
| `_io_lock` 串行化所有 DLL 调用 | 多线程无锁同时碰 `hSimConnect` |
| 写入队列（未来）：`set`/`trigger` 入队，dispatch 线程 drain | 改 ctypes 结构体 `_pack_`（必须与 MSFS SDK 布局一致） |
| `stop_background_dispatch() -> bool` + zombie/`force` 恢复 | 假设 `CallDispatch` 可在 Python 侧被中断 |

## 推荐连接顺序（多路订阅）

```python
sc.connect("MyApp", start_dispatch=False)
sc.subscribe_many(FIELDS, on_data)
sc.start_background_dispatch()  # 或 ensure_background_dispatch()
```

## 写入与天气

订阅活跃时：

- **短期**：`with sc.with_paused_dispatch(): sc.set(...); sc.trigger(...)`
- **长期**：库内写入队列，由 pump 线程串行执行

## 健康检查

勿仅用 `_dispatch_running`：

```python
sc.dispatch_thread_alive
sc.dispatch_zombie
sc.is_dataflow_healthy(max_stale=2.0)
sc.restart_dispatch(force=True)  # zombie 后恢复
```

## 字符串 SimVar（MSFS）

TITLE / ATC TYPE 等为 **null-terminated C 字符串**，不是 STRINGV 长度前缀。见 v0.5.3 的 `parsing.py` 与 `get_string()` / `subscribe_string()`。

## 版本对照

| 能力 | 版本 |
|------|------|
| STRINGV / C 字符串修复 | v0.5.3 |
| `_io_lock`、`get()` 不双 pump、dispatch 健康 API、`with_paused_dispatch` | v0.5.4 |
| 写入队列 `submit_set` / `submit_trigger` | 计划中 |
