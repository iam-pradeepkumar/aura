"""Distance and rate-tracking utilities for alert thresholds."""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, field


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points in kilometres."""
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(1.0, a)))


@dataclass
class RateTracker:
    """Track event rate over a sliding time window."""

    window_sec: float = 3600.0
    _events: deque[float] = field(default_factory=deque)

    def record(self, ts: float | None = None) -> None:
        now = ts if ts is not None else time.time()
        self._events.append(now)
        self._prune(now)

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_sec
        while self._events and self._events[0] < cutoff:
            self._events.popleft()

    def count(self) -> int:
        self._prune(time.time())
        return len(self._events)

    def rate_per_hour(self) -> float:
        self._prune(time.time())
        if not self._events:
            return 0.0
        span = max(time.time() - self._events[0], 1.0)
        return len(self._events) * 3600.0 / span

    def sum_values(self, values: deque[float]) -> float:
        return sum(values)
