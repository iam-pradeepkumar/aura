"""Wire engine, DM queue, and network dispatch together."""

from __future__ import annotations

import logging
from typing import Any

from disaster_alert.config_loader import load_config
from disaster_alert.dm_queue import DisasterManagementQueue
from disaster_alert.engine import DisasterAlertEngine
from disaster_alert.models import DisasterAlert
from disaster_alert.notify.lan_server import LanAlertServer
from disaster_alert.notify.network_dispatch import NetworkDispatcher

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


def _on_alert_from_engine(alert: DisasterAlert) -> None:
    """Route new alerts into the DM approval queue."""
    dm_enabled = bool(
        (load_config().get("notify") or {}).get("disaster_management", {}).get("enabled", True)
    )
    if dm_enabled and alert.alert_type.value != "test":
        get_queue().enqueue(alert)
    else:
        _broadcast_approved(alert)


def _broadcast_approved(item_or_alert) -> None:
    from disaster_alert.dm_queue import QueuedAlert

    if isinstance(item_or_alert, QueuedAlert):
        alert = item_or_alert.alert
        get_queue().mark_broadcast(alert.id)
    else:
        alert = item_or_alert
    result = get_dispatcher().dispatch(alert)
    logger.info("Broadcast alert %s: %s", alert.id, result)


def create_engine(
    config: dict[str, Any] | None = None,
    *,
    start_lan_server: bool = True,
) -> DisasterAlertEngine:
    """Create and wire the disaster alert engine with listeners."""
    global _engine, _queue, _dispatcher, _lan_server

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
            return [a.to_dict() for a in _engine.last_alerts] if _engine else []

        def _status() -> dict:
            return _engine.status() if _engine else {}

        _lan_server = LanAlertServer(port=port, alert_provider=_alerts, status_provider=_status)
        _lan_server.start()

    logger.info(
        "Disaster alert engine ready (role=%s)",
        (cfg.get("alert_node") or {}).get("role", "single_monitor"),
    )
    return _engine
