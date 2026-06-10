"""SimConnect 读数诊断 — MSFS 进入飞行后运行。

用法:
    pip install -e .
    python examples/diagnose_read.py

可选：指定 SDK DLL
    set SIMCONNECT_DLL=D:\\MSFS SDK\\SimConnect SDK\\lib\\SimConnect.dll
"""
import logging
import math
import os
import sys
import time
from ctypes import cast, c_void_p

from simconnect_native.constants import SIMCONNECT_RECV_ID_ASSIGNED_OBJECT_ID
from simconnect_native import (
    SimConnect,
    SIMCONNECT_PERIOD_SIM_FRAME,
    SIMCONNECT_RECV_ID_EXCEPTION,
    SIMCONNECT_RECV_ID_EVENT,
    SIMCONNECT_RECV_ID_OPEN,
    SIMCONNECT_RECV_ID_QUIT,
    SIMCONNECT_RECV_ID_SIMOBJECT_DATA,
    SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE,
    describe_simconnect_dll_path,
    find_simconnect_dll,
    is_untrusted_simconnect_dll,
)
from simconnect_native.errors import SimConnectTimeoutError
from simconnect_native.structures import SIMOBJECT_DATA_HEADER

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("diagnose")

DATA_EVENTS = {
    SIMCONNECT_RECV_ID_SIMOBJECT_DATA,
    SIMCONNECT_RECV_ID_SIMOBJECT_DATA_BYTYPE,
}


def _looks_like_altitude(value: float) -> bool:
    if value is None or not math.isfinite(value):
        return False
    if abs(value) < 1e-200:
        return False
    return -2000.0 <= value <= 120000.0


def _pump(sc: SimConnect, rounds: int = 8) -> None:
    for _ in range(rounds):
        sc.dispatch()


def main() -> int:
    dll_path = find_simconnect_dll()
    logger.info("将使用 SimConnect.dll: %s", dll_path)
    source = describe_simconnect_dll_path(dll_path)
    if source:
        logger.info("%s", source)
    if "_mei" in dll_path.lower() and not os.environ.get("SIMCONNECT_DLL"):
        logger.info(
            "若要强制使用 SDK 官方 DLL，运行前执行: "
            "set SIMCONNECT_DLL=D:\\MSFS SDK\\SimConnect SDK\\lib\\SimConnect.dll"
        )
    if is_untrusted_simconnect_dll(dll_path):
        logger.warning("当前 SimConnect.dll 来自可疑目录，建议改用 SDK 可再发行版。")

    stats = {
        "open": 0,
        "data": 0,
        "exception": 0,
        "other": 0,
        "other_ids": [],
        "subscribe_hits": 0,
        "valid_hits": 0,
        "empty_data": 0,
        "events": 0,
    }
    sc = SimConnect(auto_reconnect=False)
    sc.load_dll(dll_path)

    def on_altitude(value):
        stats["subscribe_hits"] += 1
        if _looks_like_altitude(value):
            stats["valid_hits"] += 1
        if stats["subscribe_hits"] <= 5 or stats["subscribe_hits"] % 50 == 0:
            tag = "OK" if _looks_like_altitude(value) else "BAD"
            logger.info("subscribe 回调 [%s]: PLANE ALTITUDE = %s", tag, value)

    def on_dispatch(p_data, _cb_data, _ctx):
        try:
            msg_id = p_data.contents.dwID
        except Exception:
            return

        if msg_id == SIMCONNECT_RECV_ID_OPEN:
            stats["open"] += 1
            logger.info("收到 OPEN — 模拟器已就绪")
        elif msg_id == SIMCONNECT_RECV_ID_ASSIGNED_OBJECT_ID:
            obj_id = sc._parse_assigned_object_id(p_data)
            logger.info("收到用户飞机 objectID=%s", obj_id)
        elif msg_id == SIMCONNECT_RECV_ID_QUIT:
            logger.warning("收到 QUIT — 模拟器已退出")
        elif msg_id == SIMCONNECT_RECV_ID_EVENT:
            stats["events"] += 1
        elif msg_id == SIMCONNECT_RECV_ID_EXCEPTION:
            stats["exception"] += 1
            name, send_id, index = SimConnect.parse_exception(p_data)
            logger.warning("SimConnect 异常: %s send=%s index=%s", name, send_id, index)
        elif msg_id in DATA_EVENTS:
            req_id, value = sc.read_double(p_data)
            if value is None:
                stats["empty_data"] += 1
                if stats["empty_data"] <= 3:
                    try:
                        hdr = SIMOBJECT_DATA_HEADER.from_address(
                            cast(p_data, c_void_p).value
                        )
                        logger.warning(
                            "收到空数据包: msg=%s req=%s size=%s count=%s",
                            msg_id, hdr.dwRequestID, hdr.dwSize, hdr.dwDefineCount,
                        )
                    except Exception:
                        pass
                return
            stats["data"] += 1
            if stats["data"] == 1:
                try:
                    hdr = SIMOBJECT_DATA_HEADER.from_address(
                        cast(p_data, c_void_p).value
                    )
                    logger.info(
                        "首包头部: req=%s def=%s count=%s size=%s",
                        hdr.dwRequestID, hdr.dwDefineID, hdr.dwDefineCount, hdr.dwSize,
                    )
                except Exception:
                    pass
            if stats["data"] <= 5 or stats["data"] % 50 == 0:
                tag = "OK" if _looks_like_altitude(value) else "BAD"
                logger.info("dispatch 数据 [%s]: req=%s value=%s", tag, req_id, value)
        else:
            stats["other"] += 1
            if len(stats["other_ids"]) < 10:
                stats["other_ids"].append(msg_id)

    sc.set_dispatch_cb(on_dispatch)

    try:
        sc.connect(
            "SimConnectH-Diagnose",
            dll_path=dll_path,
            start_dispatch=False,
        )
    except ConnectionError as exc:
        logger.error("连接失败: %s", exc)
        logger.error("请确认 MSFS 与本程序在同一台机器、同一用户会话中运行。")
        return 1

    logger.info(
        "SimConnect 已连接 (config_index=%d, open=%s)",
        sc._config_index,
        sc._open_received,
    )

    sub_id = sc.subscribe(
        "PLANE ALTITUDE", "feet", on_altitude,
        period=SIMCONNECT_PERIOD_SIM_FRAME,
    )
    logger.info(
        "已订阅 PLANE ALTITUDE (sub_id=%s, open=%s)，等待数据…",
        sub_id, sc._open_received,
    )

    try:
        alt = sc.get("PLANE ALTITUDE", "feet", timeout=3.0)
        logger.info("同步 get() 测试: PLANE ALTITUDE = %s", alt)
    except SimConnectTimeoutError:
        logger.warning("同步 get() 3 秒内无响应（将继续订阅轮询）")
    except Exception as exc:
        logger.warning("同步 get() 失败: %s", exc)

    logger.info("诊断运行 15 秒 — 请确认已在飞行中且模拟未暂停...")
    deadline = time.time() + 15
    while time.time() < deadline:
        _pump(sc)
        time.sleep(0.01)

    sc.close()
    logger.info(
        "统计: open=%s data=%s empty=%s events=%s exception=%s "
        "subscribe=%s valid=%s other=%s",
        stats["open"], stats["data"], stats["empty_data"], stats["events"],
        stats["exception"], stats["subscribe_hits"], stats["valid_hits"],
        stats["other"],
    )
    if stats["other_ids"]:
        logger.info("未识别的消息 ID（前几条）: %s", stats["other_ids"])

    if stats["data"] == 0 and stats["subscribe_hits"] == 0:
        logger.error("15 秒内未收到任何 SimVar 数据。")
        logger.error("排查: 1) 确认已在飞行且未暂停")
        logger.error("  2) 设置 SIMCONNECT_DLL 为 SDK 官方 DLL 后重试")
        return 2
    if stats["valid_hits"] == 0:
        logger.error("收到数据但数值异常，请换 SDK 官方 SimConnect.dll 重试。")
        return 3
    if stats["exception"]:
        logger.warning("收到 SimConnect 异常，请检查 SimVar 名称与数据定义。")
    logger.info("读数链路正常。")
    return 0


if __name__ == "__main__":
    rc = main()
    if getattr(sys, "frozen", False):
        input("\n按 Enter 键退出…")
    sys.exit(rc)
