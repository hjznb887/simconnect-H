"""FastAPI telemetry bridge — optional deps, not part of simconnect_native.

Run (MSFS in flight, not paused):

    pip install -e .
    pip install -r examples/requirements-examples.txt
    uvicorn examples.fastapi_telemetry:app --host 127.0.0.1 --port 8765

Endpoints:
    GET /health    — liveness (no SimConnect)
    GET /snapshot  — JSON batch read
    GET /stream    — Server-Sent Events from subscribe_stream
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from simconnect_native import DataField, SimConnectError
from simconnect_native.asyncio import AsyncSimConnect

TELEMETRY_FIELDS = {
    "alt": DataField("PLANE ALTITUDE", "feet"),
    "ias": DataField("AIRSPEED INDICATED", "knots"),
    "hdg": DataField("PLANE HEADING DEGREES TRUE", "degrees"),
    "lat": DataField("PLANE LATITUDE", "degrees"),
    "lon": DataField("PLANE LONGITUDE", "degrees"),
    "vs": DataField("VERTICAL SPEED", "feet per minute"),
    "gs": DataField("GROUND VELOCITY", "knots"),
}


def _msfs_unavailable(detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": "msfs_unavailable", "detail": detail},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    sim: Optional[AsyncSimConnect] = None
    connect_error: Optional[str] = None
    try:
        sim = await AsyncSimConnect.connect("FastAPITelemetry")
    except SimConnectError as exc:
        connect_error = str(exc)
    except Exception as exc:  # pragma: no cover - DLL / OS errors
        connect_error = str(exc)
    app.state.sim = sim
    app.state.connect_error = connect_error
    try:
        yield
    finally:
        if sim is not None:
            await sim.close()


app = FastAPI(title="MSFS Telemetry", lifespan=lifespan)


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/snapshot")
async def snapshot(request: Request) -> Any:
    sim: Optional[AsyncSimConnect] = request.app.state.sim
    if sim is None:
        detail = request.app.state.connect_error or "MSFS not connected"
        return _msfs_unavailable(detail)
    try:
        data = await sim.get_many(TELEMETRY_FIELDS, timeout=3.0)
        return data
    except SimConnectError as exc:
        return _msfs_unavailable(str(exc))


def _sse_event(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@app.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    sim: Optional[AsyncSimConnect] = request.app.state.sim
    if sim is None:
        detail = request.app.state.connect_error or "MSFS not connected"
        return _msfs_unavailable(detail)

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for packet in sim.subscribe_stream(TELEMETRY_FIELDS):
                if await request.is_disconnected():
                    break
                yield _sse_event(packet)
        except SimConnectError as exc:
            yield _sse_event({"error": "msfs_unavailable", "detail": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
