"""Persist dashboard-editable alert settings."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from disaster_alert.config_loader import DEFAULT_SETTINGS_PATH, load_config

_lock = threading.Lock()

_DEFAULT_DM = {
    "webhook_url": "",
    "bearer_token": "",
    "broadcast_title": "EVACUATION ALERT — Vellore region",
    "broadcast_message": (
        "A hazard has been detected near your area. Move to the nearest safe zone immediately. "
        "Follow local authorities and avoid low-lying roads."
    ),
    "safe_zones": [],
    "location": None,
    "live_api_polling": True,
}


def _settings_path(path: Path | None = None) -> Path:
    p = path or DEFAULT_SETTINGS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _default_safe_zones() -> list[dict[str, Any]]:
    cfg = load_config()
    return deepcopy(cfg.get("safe_zones") or [])


def load(path: Path | None = None) -> dict[str, Any]:
    settings_path = _settings_path(path)
    out = deepcopy(_DEFAULT_DM)
    out["safe_zones"] = _default_safe_zones()
    if not settings_path.exists():
        return out
    try:
        with settings_path.open(encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except (json.JSONDecodeError, OSError):
        data = {}
    out["webhook_url"] = str(data.get("webhook_url") or "")
    out["bearer_token"] = str(data.get("bearer_token") or "")
    out["broadcast_title"] = str(data.get("broadcast_title") or out["broadcast_title"])
    out["broadcast_message"] = str(data.get("broadcast_message") or out["broadcast_message"])
    if data.get("safe_zones"):
        out["safe_zones"] = data["safe_zones"]
    if data.get("location"):
        out["location"] = data["location"]
    if "live_api_polling" in data:
        out["live_api_polling"] = bool(data["live_api_polling"])
    return out


def save(settings: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    settings_path = _settings_path(path)
    current = load(settings_path)
    for key in (
        "webhook_url",
        "bearer_token",
        "broadcast_title",
        "broadcast_message",
        "safe_zones",
        "location",
        "live_api_polling",
    ):
        if key in settings:
            current[key] = settings[key]
    with _lock:
        with settings_path.open("w", encoding="utf-8") as fh:
            json.dump(current, fh, indent=2)
            fh.write("\n")
    return current


def get_webhook_url(path: Path | None = None) -> str:
    return load(path)["webhook_url"]


def set_webhook_url(url: str, path: Path | None = None) -> str:
    return save({"webhook_url": url}, path)["webhook_url"]
