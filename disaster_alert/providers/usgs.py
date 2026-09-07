"""USGS earthquake feed provider."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from disaster_alert.models import AlertType, DisasterAlert, Severity
from disaster_alert.providers.http_util import fetch_json
from disaster_alert.threshold import haversine_km, RateTracker


def fetch_usgs_events(url: str, timeout_sec: float = 12.0) -> list[dict[str, Any]]:
    data = fetch_json(url, timeout_sec=timeout_sec)
    return list(data.get("features") or [])


def evaluate_earthquakes(
    features: list[dict[str, Any]],
    *,
    origin_lat: float,
    origin_lon: float,
    min_magnitude: float,
    max_distance_km: float,
    rate_mag_per_hour: float,
    rate_tracker: RateTracker | None = None,
) -> list[DisasterAlert]:
    alerts: list[DisasterAlert] = []
    qualifying: list[tuple[float, dict[str, Any]]] = []

    for feat in features:
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or [0, 0, 0]
        lon, lat = float(coords[0]), float(coords[1])
        mag = float(props.get("mag") or 0)
        if mag < min_magnitude:
            continue
        dist = haversine_km(origin_lat, origin_lon, lat, lon)
        if dist > max_distance_km:
            continue
        qualifying.append((mag, feat))

    if rate_tracker and qualifying:
        for mag, _ in qualifying:
            if mag >= min_magnitude:
                rate_tracker.record()

    rate = rate_tracker.rate_per_hour() if rate_tracker else 0.0
    elevated_rate = rate >= rate_mag_per_hour and rate_mag_per_hour > 0

    for mag, feat in qualifying:
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or [0, 0, 0]
        lon, lat = float(coords[0]), float(coords[1])
        dist = haversine_km(origin_lat, origin_lon, lat, lon)
        place = props.get("place") or "unknown location"
        severity = Severity.CRITICAL if mag >= 5.5 else Severity.WARNING
        if elevated_rate:
            severity = Severity.CRITICAL
        ts_ms = props.get("time")
        ts = (
            datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)
            if ts_ms
            else datetime.now(timezone.utc)
        )
        alerts.append(
            DisasterAlert(
                alert_type=AlertType.EARTHQUAKE,
                severity=severity,
                title=f"M{mag:.1f} earthquake — {place}",
                message=(
                    f"Magnitude {mag:.1f} detected {dist:.0f} km away near {place}. "
                    f"Seismic rate: {rate:.2f}/hr."
                ),
                source="usgs",
                latitude=lat,
                longitude=lon,
                distance_km=round(dist, 1),
                timestamp=ts,
                metadata={
                    "magnitude": mag,
                    "usgs_id": feat.get("id"),
                    "place": place,
                    "rate_per_hour": round(rate, 3),
                },
            )
        )
    return alerts
