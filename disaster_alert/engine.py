"""Disaster alert polling engine — primary laptop poller (single-node)."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from disaster_alert.config_loader import load_config
from disaster_alert.models import AlertType, DisasterAlert, Severity
from disaster_alert.providers.firms import evaluate_wildfires, fetch_firms_hotspots
from disaster_alert.providers.open_meteo import evaluate_weather, fetch_weather
from disaster_alert.providers.usgs import evaluate_earthquakes, fetch_usgs_events
from disaster_alert.threshold import RateTracker

logger = logging.getLogger(__name__)

AlertListener = Callable[[DisasterAlert], None]


def _is_network_error(exc: Exception) -> bool:
    import errno
    import socket

    if isinstance(exc, (socket.gaierror, socket.timeout, TimeoutError)):
        return True
    if isinstance(exc, OSError) and getattr(exc, "errno", None) in {
        errno.ENETUNREACH,
        errno.EHOSTUNREACH,
        errno.ECONNREFUSED,
        -2,
        -3,
    }:
        return True
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "name resolution",
            "temporary failure",
            "network is unreachable",
            "nodename nor servname",
            "failed to establish a new connection",
        )
    )


def _friendly_network_message() -> str:
    return (
        "No internet connection — USGS and Open-Meteo are unreachable. "
        "Use DM Console → Simulate hazard for demos, or enable Live API polling when online."
    )


class DisasterAlertEngine:
    """Poll external APIs and emit alerts that exceed configured thresholds."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = config or load_config()
        self._listeners: list[AlertListener] = []
        self._lock = threading.Lock()
        self._last_poll: datetime | None = None
        self._last_alerts: list[DisasterAlert] = []
        self._seen_ids: set[str] = set()
        self._eq_rate = RateTracker(window_sec=3600.0)
        self._errors: list[str] = []

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    @property
    def last_poll(self) -> datetime | None:
        return self._last_poll

    @property
    def last_alerts(self) -> list[DisasterAlert]:
        return list(self._last_alerts)

    @property
    def errors(self) -> list[str]:
        return list(self._errors)

    def add_listener(self, listener: AlertListener) -> None:
        self._listeners.append(listener)

    def _emit(self, alert: DisasterAlert) -> None:
        for listener in self._listeners:
            try:
                listener(alert)
            except Exception:
                logger.exception("Alert listener failed for %s", alert.id)

    def update_runtime_config(self, config: dict[str, Any]) -> None:
        with self._lock:
            self._config = config

    def poll_once(self) -> list[DisasterAlert]:
        """Fetch all providers, evaluate thresholds, return new alerts."""
        cfg = self._config
        if not cfg.get("live_api_polling", True):
            with self._lock:
                self._last_poll = datetime.now(timezone.utc)
                self._last_alerts = []
                self._errors = []
            return []

        loc = cfg.get("location") or {}
        lat = float(loc.get("latitude", 0))
        lon = float(loc.get("longitude", 0))
        api = cfg.get("api") or {}
        thresholds = cfg.get("thresholds") or {}
        new_alerts: list[DisasterAlert] = []
        errors: list[str] = []

        # USGS earthquakes
        eq_cfg = thresholds.get("earthquake") or {}
        try:
            features = fetch_usgs_events(
                api.get("usgs_url", ""),
                timeout_sec=float(
                    (cfg.get("notify") or {}).get("disaster_management", {}).get("timeout_sec", 12)
                ),
            )
            eq_alerts = evaluate_earthquakes(
                features,
                origin_lat=lat,
                origin_lon=lon,
                min_magnitude=float(eq_cfg.get("min_magnitude", 4.0)),
                max_distance_km=float(eq_cfg.get("max_distance_km", 300)),
                rate_mag_per_hour=float(eq_cfg.get("rate_mag_per_hour", 0.5)),
                rate_tracker=self._eq_rate,
            )
            new_alerts.extend(eq_alerts)
        except Exception as exc:
            msg = f"USGS poll failed: {exc}"
            logger.warning(msg)
            errors.append(msg if not _is_network_error(exc) else "USGS: offline (no internet)")

        # Open-Meteo weather
        wx_cfg = thresholds.get("weather") or {}
        try:
            weather = fetch_weather(api.get("open_meteo_url", ""), lat, lon)
            wx_alerts = evaluate_weather(
                weather,
                origin_lat=lat,
                origin_lon=lon,
                wind_speed_mps=float(wx_cfg.get("wind_speed_mps", 17.0)),
                wind_gust_mps=float(wx_cfg.get("wind_gust_mps", 22.0)),
                precipitation_mm_h=float(wx_cfg.get("precipitation_mm_h", 8.0)),
                precip_rate_increase_mm_h=float(wx_cfg.get("precip_rate_increase_mm_h", 4.0)),
                storm_indicator_score=float(wx_cfg.get("storm_indicator_score", 0.65)),
            )
            new_alerts.extend(wx_alerts)
        except Exception as exc:
            msg = f"Open-Meteo poll failed: {exc}"
            logger.warning(msg)
            errors.append(msg if not _is_network_error(exc) else "Open-Meteo: offline (no internet)")

        # NASA FIRMS wildfire (skipped when no API key)
        wf_cfg = thresholds.get("wildfire") or {}
        firms_key = str(api.get("firms_map_key") or "")
        if firms_key:
            try:
                hotspots = fetch_firms_hotspots(firms_key, lat, lon)
                wf_alerts = evaluate_wildfires(
                    hotspots,
                    origin_lat=lat,
                    origin_lon=lon,
                    min_frp=float(wf_cfg.get("min_frp", 15.0)),
                    max_distance_km=float(wf_cfg.get("max_distance_km", 80)),
                    hotspot_count_warning=int(wf_cfg.get("hotspot_count_warning", 3)),
                )
                new_alerts.extend(wf_alerts)
            except Exception as exc:
                msg = f"FIRMS poll failed: {exc}"
                logger.warning(msg)
                errors.append(msg)

        with self._lock:
            self._last_poll = datetime.now(timezone.utc)
            self._last_alerts = new_alerts
            self._errors = errors

            deduped: list[DisasterAlert] = []
            for alert in new_alerts:
                key = f"{alert.alert_type.value}:{alert.title}"
                if key in self._seen_ids:
                    continue
                self._seen_ids.add(key)
                deduped.append(alert)
                self._emit(alert)

            # Keep seen set bounded
            if len(self._seen_ids) > 500:
                self._seen_ids = set(list(self._seen_ids)[-250:])

        return deduped

    def create_test_alert(self, message: str = "Test alert from disaster_alert engine") -> DisasterAlert:
        loc = self._config.get("location") or {}
        lat = float(loc.get("latitude", 12.334258))
        lon = float(loc.get("longitude", 79.783187))
        alert = DisasterAlert(
            alert_type=AlertType.EARTHQUAKE,
            severity=Severity.WARNING,
            title="M4.2 earthquake detected — demo alert",
            message=message or (
                "USGS feed reports elevated seismic activity within 120 km of Vellore. "
                "This is a DM console test — verify message, safe zones, then broadcast."
            ),
            source="dm_test",
            latitude=lat,
            longitude=lon,
            distance_km=48.0,
            metadata={
                "demo": True,
                "magnitude": 4.2,
                "depth_km": 10,
                "region": loc.get("name", "Vellore region, India"),
            },
        )
        self._emit(alert)
        return alert

    def status(self) -> dict[str, Any]:
        errors = list(self._errors)
        live_polling = bool(self._config.get("live_api_polling", True))
        network_offline = live_polling and bool(errors) and all(
            "offline" in e.lower() or "no internet" in e.lower() for e in errors
        )
        if network_offline:
            errors = [_friendly_network_message()]

        def _source_state(provider: str) -> str:
            if not live_polling:
                return "paused"
            if any(provider in e for e in self._errors):
                if network_offline or any("offline" in e for e in self._errors if provider in e):
                    return "offline"
                return "error"
            return "ok"

        sources = {
            "USGS": _source_state("USGS"),
            "Open-Meteo": _source_state("Open-Meteo"),
            "FIRMS": "skipped"
            if not str((self._config.get("api") or {}).get("firms_map_key") or "")
            else _source_state("FIRMS"),
        }
        last_ts = self._last_poll.timestamp() if self._last_poll else None
        degraded = bool(errors) and live_polling and not network_offline
        return {
            "ok": self._last_poll is not None and not degraded,
            "network_offline": network_offline,
            "live_api_polling": live_polling,
            "role": (self._config.get("alert_node") or {}).get("role", "single_monitor"),
            "last_poll": last_ts,
            "alert_count": len(self._last_alerts),
            "errors": errors,
            "sources": sources,
            "location": self._config.get("location"),
            "poll_interval_sec": self._config.get("poll_interval_sec", 120),
        }
