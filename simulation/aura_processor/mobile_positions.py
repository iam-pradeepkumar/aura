"""Runtime node position store for mobile CSI sensing."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock


@dataclass
class NodePositionStore:
    """Thread-safe mutable node positions (meters, world frame)."""

    positions: dict[int, tuple[float, float]] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def update(self, positions: dict[int, tuple[float, float]]) -> None:
        with self._lock:
            for nid, xy in positions.items():
                self.positions[int(nid)] = (float(xy[0]), float(xy[1]))

    def get(self, node_id: int, default: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
        with self._lock:
            return self.positions.get(int(node_id), default)

    def as_dict(self) -> dict[int, tuple[float, float]]:
        with self._lock:
            return dict(self.positions)
