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


def survivors_geo_to_local(
    anchor: GeoAnchor,
    survivors_geo: list,
    local_poly: list[tuple[float, float]] | None = None,
) -> list[dict]:
    """Convert user-placed lat/lon survivors into local meter victims (trust map placement)."""
    out: list[dict] = []
    for i, raw in enumerate(survivors_geo):
        if isinstance(raw, (list, tuple)) and len(raw) >= 2:
            lon, lat = float(raw[0]), float(raw[1])
            vid = i + 1
        else:
            lat = float(raw.get("lat"))
            lon = float(raw.get("lon"))
            vid = int(raw.get("id", i + 1))
        x, y = anchor.to_local(lat, lon)
        out.append({
            "id": vid,
            "x": x,
            "y": y,
            "resp_bpm": float(raw.get("resp_bpm", 12 + (i % 5))) if not isinstance(raw, (list, tuple)) else float(12 + (i % 5)),
            "lat": lat,
            "lon": lon,
        })
    return out


def survivors_geo_lookup(survivors_geo: list | None) -> dict[int, tuple[float, float]]:
    """Authoritative lat/lon for each placed survivor from the client payload."""
    out: dict[int, tuple[float, float]] = {}
    for i, raw in enumerate(survivors_geo or []):
        if isinstance(raw, (list, tuple)) and len(raw) >= 2:
            lon, lat = float(raw[0]), float(raw[1])
            vid = i + 1
        else:
            lat = float(raw.get("lat"))
            lon = float(raw.get("lon"))
            vid = int(raw.get("id", i + 1))
        if vid:
            out[vid] = (lat, lon)
    return out
