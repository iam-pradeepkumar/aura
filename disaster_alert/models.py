"""Data models for disaster alerts."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class AlertType(str, Enum):
    EARTHQUAKE = "earthquake"
    WEATHER = "weather"
    WILDFIRE = "wildfire"
    TEST = "test"


class Severity(str, Enum):
    INFO = "info"
    ADVISORY = "advisory"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class DisasterAlert:
    alert_type: AlertType
    severity: Severity
    title: str
    message: str
    source: str
    latitude: float | None = None
    longitude: float | None = None
    distance_km: float | None = None
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["alert_type"] = self.alert_type.value
        data["severity"] = self.severity.value
        data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DisasterAlert:
        ts = data.get("timestamp")
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        elif ts is None:
            ts = datetime.now(timezone.utc)
        return cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            alert_type=AlertType(data["alert_type"]),
            severity=Severity(data["severity"]),
            title=data["title"],
            message=data["message"],
            source=data.get("source", "unknown"),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            distance_km=data.get("distance_km"),
            timestamp=ts,
            metadata=data.get("metadata") or {},
        )
