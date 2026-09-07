"""Disaster management approval queue."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from disaster_alert.models import DisasterAlert


class QueueStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    BROADCAST = "broadcast"


@dataclass
class QueuedAlert:
    alert: DisasterAlert
    status: QueueStatus = QueueStatus.PENDING
    queued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    decided_at: datetime | None = None
    note: str = ""
    custom_title: str = ""
    custom_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.alert.id,
            "status": self.status.value,
            "queued_at": self.queued_at.isoformat(),
            "decided_at": self.decided_at.isoformat() if self.decided_at else None,
            "note": self.note,
            "custom_title": self.custom_title,
            "custom_message": self.custom_message,
            "alert": self.alert.to_dict(),
        }


class DisasterManagementQueue:
    """Hold alerts pending DM approval before network broadcast."""

    def __init__(self) -> None:
        self._items: dict[str, QueuedAlert] = {}
        self._lock = threading.Lock()
        self._on_approved: list = []

    def add_listener_on_approved(self, callback) -> None:
        self._on_approved.append(callback)

    def enqueue(self, alert: DisasterAlert) -> QueuedAlert:
        with self._lock:
            item = QueuedAlert(alert=alert)
            self._items[alert.id] = item
            return item

    def get(self, alert_id: str) -> QueuedAlert | None:
        with self._lock:
            return self._items.get(alert_id)

    def list_all(self) -> list[QueuedAlert]:
        with self._lock:
            return list(self._items.values())

    def list_pending(self) -> list[QueuedAlert]:
        with self._lock:
            return [i for i in self._items.values() if i.status == QueueStatus.PENDING]

    def list_broadcast(self) -> list[QueuedAlert]:
        with self._lock:
            return [
                i for i in self._items.values()
                if i.status in (QueueStatus.APPROVED, QueueStatus.BROADCAST)
            ]

    def update_pending(
        self,
        alert_id: str,
        *,
        custom_title: str | None = None,
        custom_message: str | None = None,
        note: str | None = None,
    ) -> QueuedAlert | None:
        with self._lock:
            item = self._items.get(alert_id)
            if not item or item.status != QueueStatus.PENDING:
                return None
            if custom_title is not None:
                item.custom_title = custom_title
            if custom_message is not None:
                item.custom_message = custom_message
            if note is not None:
                item.note = note
            return item

    def approve(
        self,
        alert_id: str,
        note: str = "",
        *,
        custom_title: str = "",
        custom_message: str = "",
    ) -> QueuedAlert | None:
        with self._lock:
            item = self._items.get(alert_id)
            if not item or item.status != QueueStatus.PENDING:
                return None
            if custom_title:
                item.custom_title = custom_title
            if custom_message:
                item.custom_message = custom_message
            item.status = QueueStatus.APPROVED
            item.decided_at = datetime.now(timezone.utc)
            item.note = note
        for cb in self._on_approved:
            try:
                cb(item)
            except Exception:
                pass
        return item

    def reject(self, alert_id: str, note: str = "") -> QueuedAlert | None:
        with self._lock:
            item = self._items.get(alert_id)
            if not item or item.status != QueueStatus.PENDING:
                return None
            item.status = QueueStatus.REJECTED
            item.decided_at = datetime.now(timezone.utc)
            item.note = note
            return item

    def mark_broadcast(self, alert_id: str) -> QueuedAlert | None:
        with self._lock:
            item = self._items.get(alert_id)
            if not item:
                return None
            item.status = QueueStatus.BROADCAST
            return item
