"""LAN multicast and webhook notification dispatch."""

from __future__ import annotations

import json
import logging
import socket
from typing import Any

from disaster_alert.models import DisasterAlert
from disaster_alert.providers.http_util import post_json
from disaster_alert import settings_store

logger = logging.getLogger(__name__)

MULTICAST_GROUP = "239.255.0.100"


class NetworkDispatcher:
    """Broadcast alerts on LAN multicast and POST to DM webhook."""

    def __init__(self, config: dict[str, Any]) -> None:
        notify = config.get("notify") or {}
        self._lan_enabled = bool(notify.get("lan_broadcast", True))
        self._multicast_port = int(notify.get("multicast_port", 5558))
        dm = notify.get("disaster_management") or {}
        self._dm_enabled = bool(dm.get("enabled", True))
        self._timeout_sec = float(dm.get("timeout_sec", 12))
        self._default_bearer = str(dm.get("bearer_token") or "")

    def _current_webhook(self) -> str:
        stored = settings_store.get_webhook_url()
        if stored:
            return stored
        return ""

    def _current_bearer(self) -> str:
        stored = settings_store.load().get("bearer_token", "")
        return stored or self._default_bearer

    def dispatch_lan(self, alert: DisasterAlert) -> bool:
        if not self._lan_enabled:
            return False
        payload = json.dumps({"type": "disaster_alert", "alert": alert.to_dict()}).encode("utf-8")
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
            sock.sendto(payload, (MULTICAST_GROUP, self._multicast_port))
            sock.close()
            return True
        except OSError as exc:
            logger.warning("LAN multicast failed: %s", exc)
            return False

    def dispatch_webhook(
        self, alert: DisasterAlert, extra: dict[str, Any] | None = None
    ) -> tuple[bool, str]:
        if not self._dm_enabled:
            return False, "disaster_management disabled"
        url = self._current_webhook()
        if not url:
            return False, "no webhook_url configured (LAN multicast still sent)"
        headers: dict[str, str] = {}
        bearer = self._current_bearer()
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        body: dict[str, Any] = {"alert": alert.to_dict()}
        if extra:
            body.update(extra)
        try:
            status, resp = post_json(
                url,
                body,
                timeout_sec=self._timeout_sec,
                headers=headers,
            )
            ok = 200 <= status < 300
            return ok, f"HTTP {status}: {resp[:200]}"
        except Exception as exc:
            return False, str(exc)

    def dispatch(self, alert: DisasterAlert, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        lan_ok = self.dispatch_lan(alert)
        webhook_ok, webhook_msg = self.dispatch_webhook(alert, extra=extra)
        return {
            "lan": lan_ok,
            "webhook": webhook_ok,
            "webhook_detail": webhook_msg,
        }
