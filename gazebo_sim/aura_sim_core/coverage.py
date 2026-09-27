"""Coverage planners — drone lawnmower + ground robot obstacle-aware path."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .world import DisasterWorld


@dataclass
class Waypoint:
    x: float
    y: float
    z: float = 0.0


class CoveragePlanner:
    def __init__(self, world: DisasterWorld, lane_spacing_m: float = 4.0):
        self.world = world
        self.lane_spacing = lane_spacing_m

    def _bbox(self, polygon: list[tuple[float, float]]) -> tuple[float, float, float, float]:
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        return min(xs), min(ys), max(xs), max(ys)

    def drone_lawnmower(self, altitude_m: float = 6.0) -> list[Waypoint]:
        xmin, ymin, xmax, ymax = self._bbox(self.world.zone_polygon)
        waypoints: list[Waypoint] = []
        y = ymin + 2.0
        direction = 1
        while y <= ymax - 1.0:
            if direction > 0:
                xs = [xmin + 2.0, xmax - 2.0]
            else:
                xs = [xmax - 2.0, xmin + 2.0]
            for x in xs:
                if self.world.in_zone(x, y):
                    waypoints.append(Waypoint(x, y, altitude_m))
            y += self.lane_spacing
            direction *= -1
        return waypoints

    def ground_patrol(self, step_m: float = 2.5) -> list[Waypoint]:
        """Grid patrol inside ground sub-cell, skipping obstacle discs."""
        xmin, ymin, xmax, ymax = self._bbox(self.world.ground_subcell)
        waypoints: list[Waypoint] = []
        y = ymin + 1.5
        direction = 1
        while y <= ymax - 1.0:
            xs = np.linspace(xmin + 1.5, xmax - 1.5, max(int((xmax - xmin) / step_m), 2))
            if direction < 0:
                xs = list(reversed(xs))
            for x in xs:
                if not self.world.in_ground_subcell(x, y):
                    continue
                if self.world.collides(x, y):
                    continue
                waypoints.append(Waypoint(x, y, 0.0))
            y += step_m
            direction *= -1
        return waypoints

    def ground_nav2_style(self, step_m: float = 2.0) -> list[Waypoint]:
        """Obstacle-avoiding greedy path (Nav2 stand-in for sim without ROS)."""
        raw = self.ground_patrol(step_m=step_m)
        if not raw:
            return raw
        smooth: list[Waypoint] = [raw[0]]
        for wp in raw[1:]:
            last = smooth[-1]
            if self._segment_clear(last.x, last.y, wp.x, wp.y):
                smooth.append(wp)
            else:
                mid = Waypoint((last.x + wp.x) / 2, (last.y + wp.y) / 2, 0.0)
                if not self.world.collides(mid.x, mid.y) and self.world.in_ground_subcell(mid.x, mid.y):
                    smooth.append(mid)
                smooth.append(wp)
        return smooth

    def _segment_clear(self, x0: float, y0: float, x1: float, y1: float, n: int = 8) -> bool:
        for i in range(n + 1):
            t = i / n
            x = x0 + t * (x1 - x0)
            y = y0 + t * (y1 - y0)
            if self.world.collides(x, y):
                return False
        return True
