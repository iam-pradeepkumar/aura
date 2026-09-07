"""Persist dashboard-editable alert settings (webhook URL, bearer token)."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from disaster_alert.config_loader import DEFAULT_SETTINGS_PATH

_lock = threading.Lock()


def _settings_path(path: Path | None = None) -> Path:
    p = path or DEFAULT_SETTINGS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load(path: Path | None = None) -> dict[str, Any]:
    settings_path = _settings_path(path)
    if not settings_path.exists():
        return {"webhook_url": "", "bearer_token": ""}
    try:
        with settings_path.open(encoding="utf-8") as fh:
            data = json.load(fh) or {}
    except (json.JSONDecodeError, OSError):
        data = {}
    return {
        "webhook_url": str(data.get("webhook_url") or ""),
        "bearer_token": str(data.get("bearer_token") or ""),
    }


def save(settings: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    settings_path = _settings_path(path)
    current = load(settings_path)
    if "webhook_url" in settings:
        current["webhook_url"] = str(settings["webhook_url"] or "")
    if "bearer_token" in settings:
        current["bearer_token"] = str(settings["bearer_token"] or "")
    with _lock:
        with settings_path.open("w", encoding="utf-8") as fh:
            json.dump(current, fh, indent=2)
            fh.write("\n")
    return current


def get_webhook_url(path: Path | None = None) -> str:
    return load(path)["webhook_url"]


def set_webhook_url(url: str, path: Path | None = None) -> str:
    return save({"webhook_url": url}, path)["webhook_url"]
