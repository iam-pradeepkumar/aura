"""WiFi CSI signal model — bearing + strength toward survivors for homing behavior."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .world import DisasterWorld, Victim


@dataclass
class WiFiReading:
    victim_id: int
    strength: float  # 0..1
    bearing_rad: float
    distance_m: float


class WiFiSensor:
    """Directional WiFi presence — spiderbots steer toward strongest respiration signature."""

    def __init__(self, world: DisasterWorld, sense_range_m: float = 18.0):
        self.world = world
        self.sense_range_m = sense_range_m

    def scan(self, x: float, y: float, skip_ids: set[int] | None = None) -> WiFiReading | None:
        skip = skip_ids or set()
        best: WiFiReading | None = None
        for victim in self.world.victims:
            if victim.id in skip:
                continue
            dx = victim.x - x
            dy = victim.y - y
            dist = math.hypot(dx, dy)
            if dist > self.sense_range_m:
                continue
            strength = max(0.0, (1.0 - dist / self.sense_range_m) ** 1.6)
            if best is None or strength > best.strength:
                best = WiFiReading(
                    victim_id=victim.id,
                    strength=strength,
                    bearing_rad=math.atan2(dy, dx),
                    distance_m=dist,
                )
        return best
