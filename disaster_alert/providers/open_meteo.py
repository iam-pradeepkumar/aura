"""Open-Meteo weather forecast provider."""

from __future__ import annotations

from typing import Any

from disaster_alert.models import AlertType, DisasterAlert, Severity
from disaster_alert.providers.http_util import fetch_json


def fetch_weather(
    base_url: str,
    lat: float,
    lon: float,
    timeout_sec: float = 12.0,
) -> dict[str, Any]:
    params = (
        f"?latitude={lat}&longitude={lon}"
        "&current=wind_speed_10m,wind_gusts_10m,precipitation"
        "&hourly=precipitation,wind_speed_10m,wind_gusts_10m"
        "&wind_speed_unit=ms"
        "&precipitation_unit=mm"
        "&forecast_days=1"
    )
    return fetch_json(f"{base_url.rstrip('/')}{params}", timeout_sec=timeout_sec)


def evaluate_weather(
    data: dict[str, Any],
    *,
    origin_lat: float,
    origin_lon: float,
    wind_speed_mps: float,
    wind_gust_mps: float,
    precipitation_mm_h: float,
    precip_rate_increase_mm_h: float,
    storm_indicator_score: float,
) -> list[DisasterAlert]:
    alerts: list[DisasterAlert] = []
    current = data.get("current") or {}
    hourly = data.get("hourly") or {}

    wind = float(current.get("wind_speed_10m") or 0)
    gust = float(current.get("wind_gusts_10m") or 0)
    precip = float(current.get("precipitation") or 0)

    hourly_precip = [float(x or 0) for x in (hourly.get("precipitation") or [])[:6]]
    precip_delta = 0.0
    if len(hourly_precip) >= 2:
        precip_delta = hourly_precip[-1] - hourly_precip[0]

    storm_score = 0.0
    if wind_speed_mps > 0:
        storm_score += min(wind / wind_speed_mps, 1.0) * 0.4
    if wind_gust_mps > 0:
        storm_score += min(gust / wind_gust_mps, 1.0) * 0.3
    if precipitation_mm_h > 0:
        storm_score += min(precip / precipitation_mm_h, 1.0) * 0.3

    triggered = (
        wind >= wind_speed_mps
        or gust >= wind_gust_mps
        or precip >= precipitation_mm_h
        or precip_delta >= precip_rate_increase_mm_h
        or storm_score >= storm_indicator_score
    )
    if not triggered:
        return alerts

    severity = Severity.CRITICAL if storm_score >= 0.85 else Severity.WARNING
    alerts.append(
        DisasterAlert(
            alert_type=AlertType.WEATHER,
            severity=severity,
            title="Severe weather conditions",
            message=(
                f"Wind {wind:.1f} m/s (gusts {gust:.1f} m/s), "
                f"precipitation {precip:.1f} mm/h, storm score {storm_score:.2f}."
            ),
            source="open_meteo",
            latitude=origin_lat,
            longitude=origin_lon,
            distance_km=0.0,
            metadata={
                "wind_speed_mps": wind,
                "wind_gust_mps": gust,
                "precipitation_mm_h": precip,
                "precip_delta_mm_h": precip_delta,
                "storm_score": round(storm_score, 3),
            },
        )
    )
    return alerts
