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
LANDING_DIST = STATIC_DIR / "landing-dist"
APP_VERSION = "4.2.0"

app = FastAPI(title="AURA Command Center", version=APP_VERSION)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if (LANDING_DIST / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=LANDING_DIST / "assets"),
        name="landing-assets",
    )


@app.get("/", response_model=None)
async def landing_page():
    built = LANDING_DIST / "index.html"
    if built.is_file():
        return FileResponse(built)
    return HTMLResponse((STATIC_DIR / "landing.html").read_text())


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
async def command_status(session_id: str = "") -> dict:
    from dashboard.command_sim import get_status

    if not session_id.strip():
        return {"mission_status": "idle", "running": False}
    return get_status(session_id.strip())


@app.post("/api/command/start")
async def command_start(payload: dict = Body(...)) -> dict:
    from dashboard.command_sim import start_mission

    session_id = str(payload.get("session_id", "")).strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    return await asyncio.to_thread(start_mission, session_id, payload)


@app.post("/api/command/stop")
async def command_stop(session_id: str = "") -> dict:
    from dashboard.command_sim import stop_mission

    if not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id required")
    stop_mission(session_id.strip())
    return {"status": "stopped", "session_id": session_id.strip()}


@app.websocket("/ws/command")
async def ws_command(websocket: WebSocket, session_id: str = "") -> None:
    from dashboard.command_sim import MissionManager, get_latest_frame
    from aura_sim_core.sim_tuning import WS_PUSH_HZ

    sid = session_id.strip()
    if not sid:
        await websocket.close(code=4400, reason="session_id required")
        return

    MissionManager.register_ws(sid)
    await websocket.accept()
    interval = 1.0 / WS_PUSH_HZ
    try:
        while True:
            frame = await asyncio.to_thread(get_latest_frame, sid)
            if frame:
                await websocket.send_json(frame)
            await asyncio.sleep(interval)
    except WebSocketDisconnect:
        pass
    finally:
        MissionManager.unregister_ws(sid)
