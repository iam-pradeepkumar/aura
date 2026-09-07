"""FastAPI router for disaster alert dashboard integration."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from disaster_alert import settings_store
from disaster_alert.config_loader import load_config
from disaster_alert.service import (
    create_engine,
    get_engine,
    get_queue,
    list_public_alerts,
    reload_engine_config,
)

router = APIRouter(prefix="/api/alerts", tags=["disaster-alerts"])

_ws_clients: list[WebSocket] = []


class SettingsBody(BaseModel):
    webhook_url: str | None = None
    bearer_token: str | None = None
    broadcast_title: str | None = None
    broadcast_message: str | None = None
    safe_zones: list[dict[str, Any]] | None = None
    location: dict[str, Any] | None = None
    live_api_polling: bool | None = None


class TestBody(BaseModel):
    message: str = ""
    alert_type: str = "earthquake"


class ApproveBody(BaseModel):
    note: str = ""
    custom_title: str = ""
    custom_message: str = ""


class UpdatePendingBody(BaseModel):
    custom_title: str | None = None
    custom_message: str | None = None
    note: str | None = None


class SafeZoneBody(BaseModel):
    name: str
    lat: float
    lon: float
    note: str = ""


async def _broadcast_ws(payload: dict[str, Any]) -> None:
    dead: list[WebSocket] = []
    for ws in _ws_clients:
        try:
            await ws.send_json(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)


def _ensure_engine():
    try:
        return get_engine()
    except RuntimeError:
        return create_engine()


@router.get("/status")
async def alerts_status():
    engine = _ensure_engine()
    return engine.status()


@router.get("/list")
async def alerts_list():
    """Public broadcast alerts approved by DM."""
    _ensure_engine()
    return {"alerts": list_public_alerts()}


@router.get("/monitor")
async def alerts_monitor():
    """Raw hazard detections from latest API poll (not yet broadcast)."""
    engine = _ensure_engine()
    return {"hazards": [a.to_dict() for a in engine.last_alerts]}


@router.get("/pending")
async def alerts_pending():
    _ensure_engine()
    queue = get_queue()
    return {"pending": [i.to_dict() for i in queue.list_pending()]}


@router.post("/poll")
async def alerts_poll():
    engine = _ensure_engine()
    alerts = await asyncio.to_thread(engine.poll_once)
    payload = {"type": "poll_complete", "alerts": [a.to_dict() for a in alerts]}
    await _broadcast_ws(payload)
    return {"polled": len(alerts), "alerts": [a.to_dict() for a in alerts]}


@router.post("/test")
async def alerts_test(body: TestBody | None = None):
    engine = _ensure_engine()
    msg = (body.message if body else "") or ""
    alert = engine.create_test_alert(msg)
    payload = {"type": "test_alert", "alert": alert.to_dict()}
    await _broadcast_ws(payload)
    pending = get_queue().list_pending()
    return {
        "alert": alert.to_dict(),
        "queued": True,
        "pending_id": pending[-1].alert.id if pending else alert.id,
    }


@router.get("/settings")
async def get_settings():
    cfg = load_config()
    stored = settings_store.load()
    dm = (cfg.get("notify") or {}).get("disaster_management") or {}
    return {
        "webhook_url": stored.get("webhook_url") or dm.get("webhook_url", ""),
        "bearer_token_set": bool(stored.get("bearer_token") or dm.get("bearer_token")),
        "disaster_management_enabled": bool(dm.get("enabled", True)),
        "broadcast_title": stored.get("broadcast_title", ""),
        "broadcast_message": stored.get("broadcast_message", ""),
        "safe_zones": stored.get("safe_zones") or [],
        "location": cfg.get("location"),
        "live_api_polling": bool(cfg.get("live_api_polling", True)),
    }


@router.post("/settings")
async def post_settings(body: SettingsBody):
    updates: dict[str, Any] = {}
    if body.webhook_url is not None:
        updates["webhook_url"] = body.webhook_url
    if body.bearer_token is not None:
        updates["bearer_token"] = body.bearer_token
    if body.broadcast_title is not None:
        updates["broadcast_title"] = body.broadcast_title
    if body.broadcast_message is not None:
        updates["broadcast_message"] = body.broadcast_message
    if body.safe_zones is not None:
        updates["safe_zones"] = body.safe_zones
    if body.location is not None:
        updates["location"] = body.location
    if body.live_api_polling is not None:
        updates["live_api_polling"] = body.live_api_polling
    saved = settings_store.save(updates)
    reload_engine_config()
    await _broadcast_ws({"type": "settings_updated"})
    return {"saved": True, **{k: saved[k] for k in updates}}


@router.patch("/{alert_id}/draft")
async def update_pending_draft(alert_id: str, body: UpdatePendingBody):
    _ensure_engine()
    item = get_queue().update_pending(
        alert_id,
        custom_title=body.custom_title,
        custom_message=body.custom_message,
        note=body.note,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Alert not found or not pending")
    await _broadcast_ws({"type": "pending_updated", "item": item.to_dict()})
    return item.to_dict()


@router.post("/{alert_id}/approve")
async def approve_alert(alert_id: str, body: ApproveBody | None = None):
    _ensure_engine()
    note = body.note if body else ""
    custom_title = body.custom_title if body else ""
    custom_message = body.custom_message if body else ""
    item = get_queue().approve(
        alert_id,
        note,
        custom_title=custom_title,
        custom_message=custom_message,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Alert not found or not pending")
    payload = {"type": "alert_approved", "item": item.to_dict()}
    await _broadcast_ws(payload)
    return item.to_dict()


@router.post("/{alert_id}/reject")
async def reject_alert(alert_id: str, body: ApproveBody | None = None):
    _ensure_engine()
    note = body.note if body else ""
    item = get_queue().reject(alert_id, note)
    if not item:
        raise HTTPException(status_code=404, detail="Alert not found or not pending")
    payload = {"type": "alert_rejected", "item": item.to_dict()}
    await _broadcast_ws(payload)
    return item.to_dict()


@router.get("/safe-zones")
async def safe_zones():
    stored = settings_store.load()
    return {"safe_zones": stored.get("safe_zones") or load_config().get("safe_zones") or []}


ws_router = APIRouter()


@ws_router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    engine = _ensure_engine()
    await websocket.send_json({
        "type": "connected",
        "status": engine.status(),
        "broadcast_count": len(list_public_alerts()),
    })
    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "poll":
                alerts = await asyncio.to_thread(engine.poll_once)
                await websocket.send_json(
                    {"type": "poll_complete", "alerts": [a.to_dict() for a in alerts]}
                )
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)
