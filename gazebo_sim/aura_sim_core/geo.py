"""Geographic anchor — lat/lon disaster zones to local simulation meters."""

from __future__ import annotations

import math
from dataclasses import dataclass


M_PER_DEG_LAT = 111_320.0


@dataclass
class GeoAnchor:
    lat: float
    lon: float
    label: str = ""

    def to_local(self, lat: float, lon: float) -> tuple[float, float]:
        """Meters east (x), north (y) from anchor."""
        dlat = lat - self.lat
        dlon = lon - self.lon
        y = dlat * M_PER_DEG_LAT
        x = dlon * M_PER_DEG_LAT * math.cos(math.radians(self.lat))
        return x, y

    def to_geo(self, x: float, y: float) -> tuple[float, float]:
        lat = self.lat + y / M_PER_DEG_LAT
        lon = self.lon + x / (M_PER_DEG_LAT * math.cos(math.radians(self.lat)))
        return lat, lon


def polygon_geo_to_local(anchor: GeoAnchor, ring: list[list[float]]) -> list[tuple[float, float]]:
    return [anchor.to_local(float(p[1]), float(p[0])) for p in ring]  # [lon, lat] GeoJSON order


def polygon_local_to_geo(anchor: GeoAnchor, ring: list) -> list[list[float]]:
    out = []
    for p in ring:
        lat, lon = anchor.to_geo(float(p[0]), float(p[1]))
        out.append([lon, lat])
    return out


def bbox_from_polygon(ring: list) -> tuple[float, float, float, float]:
    xs = [float(p[0]) for p in ring]
    ys = [float(p[1]) for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def area_size_from_polygon(ring: list) -> float:
    xmin, ymin, xmax, ymax = bbox_from_polygon(ring)
    return max(xmax - xmin, ymax - ymin, 20.0)
