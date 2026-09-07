"""NASA FIRMS wildfire hotspot provider (minimal)."""

from __future__ import annotations

from typing import Any

from disaster_alert.models import AlertType, DisasterAlert, Severity
from disaster_alert.threshold import haversine_km


def fetch_firms_hotspots(
    map_key: str,
    lat: float,
    lon: float,
    *,
    day_range: int = 1,
    radius_km: int = 100,
    timeout_sec: float = 12.0,
) -> list[dict[str, Any]]:
    if not map_key:
        return []
    # FIRMS area API — returns CSV; we request JSON-like parsing via area endpoint
    url = (
        "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
        f"{map_key}/VIIRS_SNPP_NRT/{lat},{lon}/{radius_km}"
    )
    try:
        import urllib.request
        import ssl

        req = urllib.request.Request(url, headers={"User-Agent": "disaster-alert/0.1"})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=timeout_sec, context=ctx) as resp:
            text = resp.read().decode("utf-8")
    except Exception:
        return []

    rows: list[dict[str, Any]] = []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return rows
    headers = [h.strip() for h in lines[0].split(",")]
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < len(headers):
            continue
        row = dict(zip(headers, parts))
        rows.append(row)
    return rows


def evaluate_wildfires(
    hotspots: list[dict[str, Any]],
    *,
    origin_lat: float,
    origin_lon: float,
    min_frp: float,
    max_distance_km: float,
    hotspot_count_warning: int,
) -> list[DisasterAlert]:
    if not hotspots:
        return []

    qualifying: list[tuple[float, float, float, dict[str, Any]]] = []
    for row in hotspots:
        try:
            lat = float(row.get("latitude") or row.get("lat") or 0)
            lon = float(row.get("longitude") or row.get("lon") or 0)
            frp = float(row.get("frp") or row.get("FRP") or 0)
        except (TypeError, ValueError):
            continue
        if frp < min_frp:
            continue
        dist = haversine_km(origin_lat, origin_lon, lat, lon)
        if dist > max_distance_km:
            continue
        qualifying.append((frp, lat, lon, row))

    if not qualifying:
        return []

    count = len(qualifying)
    max_frp = max(q[0] for q in qualifying)
    severity = (
        Severity.CRITICAL
        if count >= hotspot_count_warning or max_frp >= min_frp * 3
        else Severity.WARNING
    )
    nearest = min(qualifying, key=lambda q: haversine_km(origin_lat, origin_lon, q[1], q[2]))
    dist = haversine_km(origin_lat, origin_lon, nearest[1], nearest[2])

    return [
        DisasterAlert(
            alert_type=AlertType.WILDFIRE,
            severity=severity,
            title=f"Wildfire activity — {count} hotspot(s)",
            message=(
                f"{count} active hotspot(s) within {max_distance_km:.0f} km "
                f"(nearest {dist:.0f} km, max FRP {max_frp:.1f} MW)."
            ),
            source="firms",
            latitude=nearest[1],
            longitude=nearest[2],
            distance_km=round(dist, 1),
            metadata={
                "hotspot_count": count,
                "max_frp": max_frp,
                "nearest_frp": nearest[0],
            },
        )
    ]
