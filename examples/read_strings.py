"""字符串 SimVar 验证 — MSFS 进入飞行后运行。"""
import logging
import sys
import time

from simconnect_native import SimConnect

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

STRING_VARS = ("TITLE", "ATC TYPE", "ATC MODEL")


def main() -> int:
    with SimConnect() as sc:
        sc.connect("SimConnectH-Strings")

        for name in STRING_VARS:
            try:
                val = sc.get_string(name, timeout=3.0)
                logger.info("get_string(%s) = %r", name, val)
                if not isinstance(val, str) or not val:
                    logger.error("FAIL: %s 为空或非 str", name)
                    return 1
            except Exception as exc:
                logger.error("get_string(%s) 失败: %s", name, exc)
                return 1

        received = {}

        def on_title(s: str) -> None:
            received["TITLE"] = s
            logger.info("subscribe_string TITLE = %r", s)

        sc.subscribe_string("TITLE", on_title)
        sc.ensure_background_dispatch()
        time.sleep(3.0)

        if not received.get("TITLE"):
            logger.error("subscribe_string TITLE 未收到回调")
            return 1

    logger.info("字符串 SimVar 链路正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
