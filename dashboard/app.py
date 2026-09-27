"""AURA Command Center — SAR dashboard API (Render-ready)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STATIC_DIR = Path(__file__).resolve().parent / "static"
APP_VERSION = "4.0.0"

app = FastAPI(title="AURA Command Center", version=APP_VERSION)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def landing_page() -> str:
    return (STATIC_DIR / "landing.html").read_text()


@app.get("/command", response_class=HTMLResponse)
@app.get("/simulation", response_class=HTMLResponse)
async def command_center() -> str:
    return (STATIC_DIR / "command.html").read_text()


@app.get("/api/health")
@app.get("/api/version")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "aura-command-center",
        "version": APP_VERSION,
        "mode": "sar-command",
    }


@app.get("/favicon.ico")
async def favicon() -> FileResponse:
    return FileResponse(STATIC_DIR / "favicon.svg", media_type="image/svg+xml")


@app.get("/api/command/geocode")
async def command_geocode(q: str = "") -> dict:
    from dashboard.geocode import geocode_address

    if not q.strip():
        return {"results": []}
    try:
        return {"results": await asyncio.to_thread(geocode_address, q.strip())}
    except Exception as exc:
        return {"results": [], "error": str(exc)}


@app.get("/api/command/roster")
async def command_roster() -> dict:
    from dashboard.command_sim import get_roster

    return {"units": get_roster()}


@app.get("/api/command/zone")
async def command_zone() -> dict:
    from dashboard.command_sim import get_zone_defaults

    return get_zone_defaults()


@app.post("/api/command/disaster-scape")
async def command_disaster_scape(payload: dict = Body(...)) -> dict:
    from aura_sim_core.disaster_scape import build_scape_geo

    ring = payload.get("zone_polygon_geo") or []
    if len(ring) < 3:
        raise HTTPException(status_code=400, detail="zone_polygon_geo requires 3+ points")
    return await asyncio.to_thread(build_scape_geo, ring, payload.get("geo_anchor"))


@app.get("/api/command/status")
async def command_status() -> dict:
    from dashboard.command_sim import get_status

    return get_status()


@app.post("/api/command/start")
async def command_start(payload: dict = Body(...)) -> dict:
    from dashboard.command_sim import start_mission

    return await asyncio.to_thread(start_mission, payload)


@app.post("/api/command/stop")
async def command_stop() -> dict:
    from dashboard.command_sim import stop_mission

    stop_mission()
    return {"status": "stopped"}


@app.websocket("/ws/command")
async def ws_command(websocket: WebSocket) -> None:
    from dashboard.command_sim import get_latest_frame

    await websocket.accept()
    try:
        while True:
            frame = await asyncio.to_thread(get_latest_frame)
            if frame:
                await websocket.send_json(frame)
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
