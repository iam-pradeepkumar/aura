"""2D disaster world — polygon zone, obstacles, hidden victims."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml


@dataclass
class Victim:
    id: int
    x: float
    y: float
    resp_bpm: float = 14.0


@dataclass
class Obstacle:
    x: float
    y: float
    radius: float


@dataclass
class DisasterWorld:
    area_size_m: float
    zone_polygon: list[tuple[float, float]]
    ground_subcell: list[tuple[float, float]]
    obstacles: list[Obstacle] = field(default_factory=list)
    victims: list[Victim] = field(default_factory=list)

    def point_in_polygon(self, x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
        inside = False
        n = len(polygon)
        for i in range(n):
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % n]
            if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1):
                inside = not inside
        return inside

    def in_zone(self, x: float, y: float) -> bool:
        return self.point_in_polygon(x, y, self.zone_polygon)

    def in_ground_subcell(self, x: float, y: float) -> bool:
        return self.point_in_polygon(x, y, self.ground_subcell)

    def collides(self, x: float, y: float, margin: float = 0.35) -> bool:
        for o in self.obstacles:
            if math.hypot(x - o.x, y - o.y) < o.radius + margin:
                return True
        return False

    def nearest_victim(self, x: float, y: float) -> tuple[Victim | None, float]:
        best: Victim | None = None
        best_d = 1e9
        for v in self.victims:
            d = math.hypot(x - v.x, y - v.y)
            if d < best_d:
                best_d = d
                best = v
        return best, best_d


def _pairs(raw: list) -> list[tuple[float, float]]:
    return [(float(p[0]), float(p[1])) for p in raw]


def load_world_config(path: str | Path | None = None) -> DisasterWorld:
    p = Path(path or Path(__file__).resolve().parents[1] / "config" / "disaster_zone.yaml")
    with p.open() as f:
        cfg = yaml.safe_load(f) or {}
    obs = [Obstacle(float(o[0]), float(o[1]), float(o[2])) for o in cfg.get("obstacles", [])]
    victims = [
        Victim(int(v["id"]), float(v["x"]), float(v["y"]), float(v.get("resp_bpm", 14)))
        for v in cfg.get("victims", [])
    ]
    return DisasterWorld(
        area_size_m=float(cfg.get("area_size_m", 40.0)),
        zone_polygon=_pairs(cfg.get("zone_polygon", [])),
        ground_subcell=_pairs(cfg.get("ground_subcell", [])),
        obstacles=obs,
        victims=victims,
    )
