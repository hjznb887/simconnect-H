"""SimVar 同步读写与事件触发示例（需 MSFS 已启动并进入飞行）。"""
import logging

from simconnect_native import SimConnect

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("read_write")


def main() -> int:
    with SimConnect() as sc:
        sc.connect("SimConnectH-ReadWrite")

        alt = sc.get("PLANE ALTITUDE", "Feet", timeout=2.0)
        logger.info("当前高度: %s ft", alt)

        # sc.set("PLANE ALTITUDE", alt + 100, "Feet")  # 慎用：会改变飞机状态

        sc.subscribe("AIRSPEED INDICATED", "Knots", lambda v: logger.info("IAS: %s", v))

        import time
        time.sleep(5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
