"""Address geocoding for SAR disaster zone placement (Nominatim / OSM)."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

_USER_AGENT = "AURA-SAR-Command/1.0 (disaster simulation; contact=local)"


def geocode_address(query: str, limit: int = 5) -> list[dict]:
    q = urllib.parse.quote(query.strip())
    url = (
        f"https://nominatim.openstreetmap.org/search?"
        f"q={q}&format=json&limit={limit}&addressdetails=1"
    )
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode())
    results = []
    for item in data:
        results.append({
            "label": item.get("display_name", query),
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
            "bbox": [float(x) for x in item.get("boundingbox", [])],
            "type": item.get("type", ""),
        })
    return results


def reverse_geocode(lat: float, lon: float) -> str:
    url = (
        f"https://nominatim.openstreetmap.org/reverse?"
        f"lat={lat}&lon={lon}&format=json"
    )
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=12) as resp:
        data = json.loads(resp.read().decode())
    return data.get("display_name", f"{lat:.5f}, {lon:.5f}")
