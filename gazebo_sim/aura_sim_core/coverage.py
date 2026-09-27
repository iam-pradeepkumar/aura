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
    def __init__(self, world: DisasterWorld, lane_spacing_m: float | None = None):
        self.world = world
        self.lane_spacing = lane_spacing_m

    def _bbox(self, polygon: list[tuple[float, float]]) -> tuple[float, float, float, float]:
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        return min(xs), min(ys), max(xs), max(ys)

    def _adaptive_spacing(self, polygon: list[tuple[float, float]]) -> tuple[float, float]:
        xmin, ymin, xmax, ymax = self._bbox(polygon)
        w = max(xmax - xmin, 1.0)
        h = max(ymax - ymin, 1.0)
        lane = self.lane_spacing if self.lane_spacing is not None else max(2.5, min(6.0, w / 5.5))
        step = max(1.8, min(5.0, min(w, h) / 7.0))
        return lane, step

    def drone_corner_coverage(self, altitude_m: float = 8.0) -> list[Waypoint]:
        """Visit polygon corners, sweep the zone, return to start corner — then stop."""
        poly = self.world.zone_polygon
        if len(poly) < 3:
            return self.drone_lawnmower(altitude_m)
        wps: list[Waypoint] = []
        for x, y in poly:
            wps.append(Waypoint(float(x), float(y), altitude_m))
        wps.extend(self.drone_lawnmower(altitude_m))
        x0, y0 = poly[0]
        wps.append(Waypoint(float(x0), float(y0), altitude_m))
        return wps

    def drone_lawnmower(self, altitude_m: float = 6.0) -> list[Waypoint]:
        poly = self.world.zone_polygon
        xmin, ymin, xmax, ymax = self._bbox(poly)
        lane, _ = self._adaptive_spacing(poly)
        margin = max(0.8, min(2.0, min(xmax - xmin, ymax - ymin) * 0.08))
        waypoints: list[Waypoint] = []
        y = ymin + margin
        direction = 1
        while y <= ymax - margin:
            if direction > 0:
                xs = [xmin + margin, xmax - margin]
            else:
                xs = [xmax - margin, xmin + margin]
            for x in xs:
                if self.world.in_zone(x, y):
                    waypoints.append(Waypoint(x, y, altitude_m))
            y += lane
            direction *= -1
        return waypoints

    def ground_patrol(
        self,
        step_m: float | None = None,
        polygon: list[tuple[float, float]] | None = None,
    ) -> list[Waypoint]:
        """Grid patrol inside polygon, skipping obstacle discs."""
        poly = polygon or self.world.zone_polygon
        xmin, ymin, xmax, ymax = self._bbox(poly)
        _, step = self._adaptive_spacing(poly)
        if step_m is not None:
            step = step_m
        margin = max(0.6, min(1.8, min(xmax - xmin, ymax - ymin) * 0.06))
        waypoints: list[Waypoint] = []
        y = ymin + margin
        direction = 1
        while y <= ymax - margin:
            xs = np.linspace(xmin + margin, xmax - margin, max(int((xmax - xmin) / step), 2))
            if direction < 0:
                xs = list(reversed(xs))
            for x in xs:
                if not self.world.point_in_polygon(x, y, poly):
                    continue
                if self.world.collides(x, y):
                    continue
                waypoints.append(Waypoint(x, y, 0.0))
            y += step
            direction *= -1
        return waypoints

    def ground_nav2_style(
        self,
        step_m: float | None = None,
        polygon: list[tuple[float, float]] | None = None,
    ) -> list[Waypoint]:
        """Obstacle-avoiding greedy path (Nav2 stand-in for sim without ROS)."""
        raw = self.ground_patrol(step_m=step_m, polygon=polygon)
        if not raw:
            return raw
        smooth: list[Waypoint] = [raw[0]]
        for wp in raw[1:]:
            last = smooth[-1]
            if self._segment_clear(last.x, last.y, wp.x, wp.y):
                smooth.append(wp)
            else:
                mid = Waypoint((last.x + wp.x) / 2, (last.y + wp.y) / 2, 0.0)
                poly = polygon or self.world.zone_polygon
                if not self.world.collides(mid.x, mid.y) and self.world.point_in_polygon(mid.x, mid.y, poly):
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


def reorder_waypoints_nearest(waypoints: list[Waypoint], start_x: float, start_y: float) -> list[Waypoint]:
    """Greedy nearest-neighbor ordering so patrol begins from the unit's spawn point."""
    if not waypoints:
        return []
    remaining = list(waypoints)
    ordered: list[Waypoint] = []
    cx, cy = start_x, start_y
    while remaining:
        best_i = min(
            range(len(remaining)),
            key=lambda i: math.hypot(remaining[i].x - cx, remaining[i].y - cy),
        )
        wp = remaining.pop(best_i)
        ordered.append(wp)
        cx, cy = wp.x, wp.y
    return ordered
