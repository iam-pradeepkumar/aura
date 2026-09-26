"""Localization helpers for sensing_v2.

Informed by techniques described in wifi-densepose-mat (depth band heuristic),
reimplemented for ESP32 CSI in AURA. Depth is low-confidence estimate only.
"""

from __future__ import annotations


def estimate_depth_band(
    rssi_dbm: float | None,
    multipath_spread: float = 0.0,
    enabled: bool = False,
) -> str | None:
    """Heuristic depth band — needs field validation."""
    if not enabled or rssi_dbm is None:
        return None

    # Weak RSSI + high spread → likely deeper / obstructed
    if rssi_dbm < -78 or multipath_spread > 0.55:
        return "deep"
    if rssi_dbm < -68 or multipath_spread > 0.35:
        return "shallow"
    return "surface"
