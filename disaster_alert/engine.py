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

    def poll_once(self) -> list[DisasterAlert]:
        """Fetch all providers, evaluate thresholds, return new alerts."""
        cfg = self._config
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
            errors.append(msg)

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
            errors.append(msg)

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
        alert = DisasterAlert(
            alert_type=AlertType.TEST,
            severity=Severity.INFO,
            title="Test Alert",
            message=message,
            source="engine",
            latitude=float((self._config.get("location") or {}).get("latitude", 0)),
            longitude=float((self._config.get("location") or {}).get("longitude", 0)),
        )
        self._emit(alert)
        return alert

    def status(self) -> dict[str, Any]:
        errors = list(self._errors)
        sources = {
            "USGS": "error" if any("USGS" in e for e in errors) else "ok",
            "Open-Meteo": "error" if any("Open-Meteo" in e for e in errors) else "ok",
            "FIRMS": "skipped"
            if not str((self._config.get("api") or {}).get("firms_map_key") or "")
            else ("error" if any("FIRMS" in e for e in errors) else "ok"),
        }
        last_ts = self._last_poll.timestamp() if self._last_poll else None
        return {
            "ok": not errors or self._last_poll is not None,
            "role": (self._config.get("alert_node") or {}).get("role", "single_monitor"),
            "last_poll": last_ts,
            "alert_count": len(self._last_alerts),
            "errors": errors,
            "sources": sources,
            "location": self._config.get("location"),
            "poll_interval_sec": self._config.get("poll_interval_sec", 120),
        }
