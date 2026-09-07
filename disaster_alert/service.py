"""Wire engine, DM queue, and network dispatch together."""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from disaster_alert.config_loader import load_config
from disaster_alert.dm_queue import DisasterManagementQueue, QueuedAlert
from disaster_alert.engine import DisasterAlertEngine
from disaster_alert.models import DisasterAlert
from disaster_alert.notify.lan_server import LanAlertServer
from disaster_alert.notify.network_dispatch import NetworkDispatcher
from disaster_alert import settings_store

logger = logging.getLogger(__name__)

_engine: DisasterAlertEngine | None = None
_queue: DisasterManagementQueue | None = None
_dispatcher: NetworkDispatcher | None = None
_lan_server: LanAlertServer | None = None


def get_engine() -> DisasterAlertEngine:
    if _engine is None:
        raise RuntimeError("Engine not initialized — call create_engine() first")
    return _engine


def get_queue() -> DisasterManagementQueue:
    if _queue is None:
        raise RuntimeError("Queue not initialized — call create_engine() first")
    return _queue


def get_dispatcher() -> NetworkDispatcher:
    if _dispatcher is None:
        raise RuntimeError("Dispatcher not initialized — call create_engine() first")
    return _dispatcher


def _effective_alert_payload(item: QueuedAlert) -> dict[str, Any]:
    """Merge DM-edited copy with hazard metadata for public broadcast."""
    stored = settings_store.load()
    alert = item.alert
    title = item.custom_title or stored.get("broadcast_title") or alert.title
    message = item.custom_message or stored.get("broadcast_message") or alert.message
    loc = load_config().get("location") or {}
    safe_zones = stored.get("safe_zones") or []
    zone_lines = "\n".join(
        f"• {z.get('name', 'Shelter')} ({z.get('lat')}, {z.get('lon')}) — {z.get('note', '')}"
        for z in safe_zones
    )
    full_message = message
    if zone_lines:
        full_message = f"{message}\n\nSafe zones:\n{zone_lines}"
    return {
        "id": alert.id,
        "alert_type": alert.alert_type.value,
        "severity": alert.severity.value,
        "title": title,
        "message": full_message,
        "short_message": message,
        "source": alert.source,
        "latitude": alert.latitude,
        "longitude": alert.longitude,
        "distance_km": alert.distance_km,
        "timestamp": alert.timestamp.isoformat(),
        "location_name": loc.get("name", ""),
        "safe_zones": safe_zones,
        "metadata": alert.metadata,
        "broadcast_at": item.decided_at.isoformat() if item.decided_at else None,
        "status": item.status.value,
    }


def _on_alert_from_engine(alert: DisasterAlert) -> None:
    """Route every new alert (including tests) into the DM approval queue."""
    dm_enabled = bool(
        (load_config().get("notify") or {}).get("disaster_management", {}).get("enabled", True)
    )
    if dm_enabled:
        stored = settings_store.load()
        item = get_queue().enqueue(alert)
        item.custom_title = stored.get("broadcast_title", "")
        item.custom_message = stored.get("broadcast_message", "")
    else:
        _broadcast_approved(alert)


def _broadcast_approved(item_or_alert) -> None:
    if isinstance(item_or_alert, QueuedAlert):
        item = item_or_alert
        payload = _effective_alert_payload(item)
        alert = deepcopy(item.alert)
        alert.title = payload["title"]
        alert.message = payload["message"]
        get_queue().mark_broadcast(alert.id)
    else:
        alert = item_or_alert
        payload = alert.to_dict()

    result = get_dispatcher().dispatch(alert, extra={"broadcast": payload})
    logger.info("Broadcast alert %s: %s", alert.id, result)


def list_public_alerts() -> list[dict[str, Any]]:
    return [_effective_alert_payload(i) for i in get_queue().list_broadcast()]


def create_engine(
    config: dict[str, Any] | None = None,
    *,
    start_lan_server: bool = True,
) -> DisasterAlertEngine:
    """Create and wire the disaster alert engine with listeners."""
    global _engine, _queue, _dispatcher, _lan_server

    if _engine is not None:
        return _engine

    cfg = config or load_config()
    _engine = DisasterAlertEngine(cfg)
    _queue = DisasterManagementQueue()
    _dispatcher = NetworkDispatcher(cfg)

    _engine.add_listener(_on_alert_from_engine)
    _queue.add_listener_on_approved(_broadcast_approved)

    if start_lan_server:
        notify = cfg.get("notify") or {}
        port = int(notify.get("lan_http_port", 8765))

        def _alerts() -> list[dict]:
            try:
                return list_public_alerts()
            except Exception:
                return []

        def _status() -> dict:
            return _engine.status() if _engine else {}

        _lan_server = LanAlertServer(port=port, alert_provider=_alerts, status_provider=_status)
        try:
            _lan_server.start()
        except OSError as exc:
            logger.warning("LAN alert server not started (port %d): %s", port, exc)

    logger.info(
        "Disaster alert engine ready (role=%s)",
        (cfg.get("alert_node") or {}).get("role", "single_monitor"),
    )
    return _engine
