"""Procedural collapsed-building + debris GeoJSON inside a disaster polygon."""

from __future__ import annotations

import random
from typing import Any

from .geo import GeoAnchor, polygon_geo_to_local, polygon_local_to_geo


def _point_in_poly(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1):
            inside = not inside
    return inside


def build_scape_geo(
    zone_polygon_geo: list,
    geo_anchor: dict | None = None,
    seed: int = 7,
) -> dict[str, Any]:
    ring_geo = [[float(p[0]), float(p[1])] for p in zone_polygon_geo]
    lngs = [p[0] for p in ring_geo]
    lats = [p[1] for p in ring_geo]
    anchor = GeoAnchor(
        float((geo_anchor or {}).get("lat", sum(lats) / len(lats))),
        float((geo_anchor or {}).get("lon", sum(lngs) / len(lngs))),
        str((geo_anchor or {}).get("label", "")),
    )
    local = polygon_geo_to_local(anchor, ring_geo)
    xs = [p[0] for p in local]
    ys = [p[1] for p in local]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    w, h = max(xmax - xmin, 8), max(ymax - ymin, 8)

    rng = random.Random(seed)
    buildings: list[dict] = []
    debris: list[dict] = []

    cols = max(2, int(w / 14))
    rows = max(2, int(h / 12))
    for row in range(rows):
        for col in range(cols):
            cx = xmin + (col + 0.5) * w / cols + rng.uniform(-2, 2)
            cy = ymin + (row + 0.5) * h / rows + rng.uniform(-2, 2)
            if not _point_in_poly(cx, cy, local):
                continue
            bw = rng.uniform(5, 10)
            bh = rng.uniform(5, 10)
            collapsed = rng.random() < 0.55
            height = rng.uniform(3, 8) if collapsed else rng.uniform(10, 22)
            ring_local = [
                (cx - bw / 2, cy - bh / 2),
                (cx + bw / 2, cy - bh / 2),
                (cx + bw / 2, cy + bh / 2),
                (cx - bw / 2, cy + bh / 2),
            ]
            ring_geo_b = polygon_local_to_geo(anchor, ring_local)
            buildings.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[*ring_geo_b, ring_geo_b[0]]]},
                "properties": {
                    "height": round(height, 1),
                    "collapsed": collapsed,
                    "damage": round(rng.uniform(0.5, 1.0), 2),
                },
            })
            for _ in range(rng.randint(3, 8)):
                dx = cx + rng.uniform(-bw, bw)
                dy = cy + rng.uniform(-bh, bh)
                if not _point_in_poly(dx, dy, local):
                    continue
                lat, lon = anchor.to_geo(dx, dy)
                debris.append({
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {"size": round(rng.uniform(0.8, 2.5), 1)},
                })

    return {
        "buildings": {"type": "FeatureCollection", "features": buildings},
        "debris": {"type": "FeatureCollection", "features": debris},
    }
