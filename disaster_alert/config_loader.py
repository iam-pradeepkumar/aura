"""Load disaster alert configuration from YAML and JSON settings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = PACKAGE_DIR / "config.yaml"
DEFAULT_SETTINGS_PATH = PACKAGE_DIR / "data" / "alert_settings.json"


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_yaml_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = path or DEFAULT_CONFIG_PATH
    if not cfg_path.exists():
        return {}
    with cfg_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_settings(path: Path | None = None) -> dict[str, Any]:
    settings_path = path or DEFAULT_SETTINGS_PATH
    if not settings_path.exists():
        return {}
    try:
        with settings_path.open(encoding="utf-8") as fh:
            return json.load(fh) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def load_config(
    config_path: Path | None = None,
    settings_path: Path | None = None,
) -> dict[str, Any]:
    """Merge config.yaml with runtime settings from data/alert_settings.json."""
    cfg = load_yaml_config(config_path)
    settings = load_settings(settings_path)

    notify = cfg.setdefault("notify", {})
    dm = notify.setdefault("disaster_management", {})

    webhook = settings.get("webhook_url")
    if webhook is not None:
        dm["webhook_url"] = webhook
    bearer = settings.get("bearer_token")
    if bearer is not None:
        dm["bearer_token"] = bearer

    return cfg
