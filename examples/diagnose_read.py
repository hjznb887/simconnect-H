"""SimConnect 读数诊断脚本 — 先启动 MSFS 并进入飞行，再运行本脚本。

用法:
    python examples/diagnose_read.py
"""
import logging
import sys
import time

from simconnect_native import (
    SimConnect,
    SIMCONNECT_RECV_ID_EXCEPTION,
    SIMCONNECT_RECV_ID_OPEN,
    SIMCONNECT_RECV_ID_QUIT,
    SIMCONNECT_RECV_ID_SIMOBJECT_DATA,
    SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("diagnose")

DATA_EVENTS = {
    SIMCONNECT_RECV_ID_SIMOBJECT_DATA,
    SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE,
}


def main() -> int:
    stats = {
        "open": 0,
        "data": 0,
        "exception": 0,
        "other": 0,
        "subscribe_hits": 0,
    }

    def on_altitude(value):
        stats["subscribe_hits"] += 1
        if stats["subscribe_hits"] <= 5 or stats["subscribe_hits"] % 50 == 0:
            logger.info("subscribe 回调: PLANE ALTITUDE = %s", value)

    def on_dispatch(p_data, _cb_data, _ctx):
        try:
            msg_id = p_data.contents.dwID
        except Exception:
            return

        if msg_id == SIMCONNECT_RECV_ID_OPEN:
            stats["open"] += 1
            logger.info("收到 OPEN — SimConnect 已连接")
        elif msg_id == SIMCONNECT_RECV_ID_QUIT:
            logger.warning("收到 QUIT — 模拟器已退出")
        elif msg_id == SIMCONNECT_RECV_ID_EXCEPTION:
            stats["exception"] += 1
            name, send_id, index = SimConnect.parse_exception(p_data)
            logger.warning("SimConnect 异常: %s send=%s index=%s", name, send_id, index)
        elif msg_id in DATA_EVENTS:
            stats["data"] += 1
            req_id, value = sc.read_double(p_data)
            if stats["data"] <= 5 or stats["data"] % 50 == 0:
                logger.info("dispatch 数据: req=%s value=%s", req_id, value)
        else:
            stats["other"] += 1

    sc = SimConnect()
    try:
        sc.open("SimConnectH-Diagnose")
    except Exception as exc:
        logger.error("连接失败: %s", exc)
        logger.error("请确认 MSFS 已启动并处于飞行中。")
        return 1

    sc.subscribe("PLANE ALTITUDE", "Feet", on_altitude)
    sc.set_dispatch_cb(on_dispatch)
    sc.start_background_dispatch()

    logger.info("诊断运行 15 秒，观察是否收到数据...")
    deadline = time.time() + 15
    while time.time() < deadline:
        time.sleep(0.5)

    sc.close()
    logger.info(
        "统计: open=%s data=%s exception=%s subscribe=%s other=%s",
        stats["open"], stats["data"], stats["exception"],
        stats["subscribe_hits"], stats["other"],
    )

    if stats["data"] == 0 and stats["subscribe_hits"] == 0:
        logger.error("15 秒内未收到任何 SimVar 数据。")
        logger.error("常见原因: 未进入飞行、SimVar/单位写错、或未持续 dispatch。")
        return 2
    if stats["exception"]:
        logger.warning("收到 SimConnect 异常，请检查 SimVar 名称与数据定义。")
    logger.info("读数链路正常。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
