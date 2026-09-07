"""FastAPI router for disaster alert dashboard integration."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from disaster_alert import settings_store
from disaster_alert.config_loader import load_config
from disaster_alert.service import create_engine, get_engine, get_queue

router = APIRouter(prefix="/api/alerts", tags=["disaster-alerts"])

_ws_clients: list[WebSocket] = []


class SettingsBody(BaseModel):
    webhook_url: str | None = None
    bearer_token: str | None = None


class TestBody(BaseModel):
    message: str = "Test alert from dashboard"


class ApproveBody(BaseModel):
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


@router.get("/status")
async def alerts_status():
    try:
        engine = get_engine()
    except RuntimeError:
        engine = create_engine()
    return engine.status()


@router.get("/list")
async def alerts_list():
    try:
        engine = get_engine()
    except RuntimeError:
        engine = create_engine()
    return {"alerts": [a.to_dict() for a in engine.last_alerts]}


@router.get("/pending")
async def alerts_pending():
    try:
        queue = get_queue()
    except RuntimeError:
        create_engine()
        queue = get_queue()
    return {"pending": [i.to_dict() for i in queue.list_pending()]}


@router.post("/poll")
async def alerts_poll():
    try:
        engine = get_engine()
    except RuntimeError:
        engine = create_engine()
    alerts = await asyncio.to_thread(engine.poll_once)
    payload = {"type": "poll_complete", "alerts": [a.to_dict() for a in alerts]}
    await _broadcast_ws(payload)
    return {"polled": len(alerts), "alerts": [a.to_dict() for a in alerts]}


@router.post("/test")
async def alerts_test(body: TestBody | None = None):
    try:
        engine = get_engine()
    except RuntimeError:
        engine = create_engine()
    msg = body.message if body else "Test alert from dashboard"
    alert = engine.create_test_alert(msg)
    payload = {"type": "test_alert", "alert": alert.to_dict()}
    await _broadcast_ws(payload)
    return {"alert": alert.to_dict()}


@router.get("/settings")
async def get_settings():
    cfg = load_config()
    stored = settings_store.load()
    dm = (cfg.get("notify") or {}).get("disaster_management") or {}
    return {
        "webhook_url": stored.get("webhook_url") or dm.get("webhook_url", ""),
        "bearer_token_set": bool(stored.get("bearer_token") or dm.get("bearer_token")),
        "disaster_management_enabled": bool(dm.get("enabled", True)),
    }


@router.post("/settings")
async def post_settings(body: SettingsBody):
    updates: dict[str, str] = {}
    if body.webhook_url is not None:
        updates["webhook_url"] = body.webhook_url
    if body.bearer_token is not None:
        updates["bearer_token"] = body.bearer_token
    saved = settings_store.save(updates)
    await _broadcast_ws({"type": "settings_updated", "webhook_url": saved["webhook_url"]})
    return {"webhook_url": saved["webhook_url"], "saved": True}


@router.post("/{alert_id}/approve")
async def approve_alert(alert_id: str, body: ApproveBody | None = None):
    try:
        queue = get_queue()
    except RuntimeError:
        create_engine()
        queue = get_queue()
    note = body.note if body else ""
    item = queue.approve(alert_id, note)
    if not item:
        raise HTTPException(status_code=404, detail="Alert not found or not pending")
    payload = {"type": "alert_approved", "item": item.to_dict()}
    await _broadcast_ws(payload)
    return item.to_dict()


@router.post("/{alert_id}/reject")
async def reject_alert(alert_id: str, body: ApproveBody | None = None):
    try:
        queue = get_queue()
    except RuntimeError:
        create_engine()
        queue = get_queue()
    note = body.note if body else ""
    item = queue.reject(alert_id, note)
    if not item:
        raise HTTPException(status_code=404, detail="Alert not found or not pending")
    payload = {"type": "alert_rejected", "item": item.to_dict()}
    await _broadcast_ws(payload)
    return item.to_dict()


@router.get("/safe-zones")
async def safe_zones():
    cfg = load_config()
    return {"safe_zones": cfg.get("safe_zones") or []}


# WebSocket mounted at /ws/alerts (outside /api prefix) — see ws_router below
ws_router = APIRouter()


@ws_router.websocket("/ws/alerts")
async def ws_alerts(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        engine = get_engine()
    except RuntimeError:
        engine = create_engine()
    await websocket.send_json({"type": "connected", "status": engine.status()})
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
