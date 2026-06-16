"""Asyncio quick start — requires MSFS in flight."""
from __future__ import annotations

import asyncio

from simconnect_native import DataField
from simconnect_native.asyncio import AsyncSimConnect


async def main() -> None:
    fields = {
        "alt": DataField("PLANE ALTITUDE", "feet"),
        "ias": DataField("AIRSPEED INDICATED", "knots"),
        "title": DataField("TITLE", "", 11),
    }
    async with AsyncSimConnect.session("AsyncQuickStart") as asc:
        print("snapshot:", await asc.get_many(fields, timeout=3.0))
        count = 0
        async for packet in asc.subscribe_stream(fields):
            print("stream:", packet)
            count += 1
            if count >= 3:
                break


if __name__ == "__main__":
    asyncio.run(main())
