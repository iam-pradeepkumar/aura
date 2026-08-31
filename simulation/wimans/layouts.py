"""WiMANS environment layouts — map location labels (a–e) to XY meters."""

from __future__ import annotations

# Approximate positions from WiMANS paper room layouts (10 m × 10 m search area).
# TX/RX are along the bottom edge; survivors are labeled A–E in each environment.
LAYOUTS: dict[str, dict[str, tuple[float, float]]] = {
    "empty_room": {
        "a": (2.5, 7.5),
        "b": (5.0, 5.0),
        "c": (7.5, 2.5),
        "d": (7.5, 7.5),
        "e": (2.5, 2.5),
    },
    "classroom": {
        "a": (2.0, 8.0),
        "b": (5.0, 6.0),
        "c": (8.0, 4.0),
        "d": (8.0, 8.0),
        "e": (2.0, 3.0),
    },
    "meeting_room": {
        "a": (3.0, 7.5),
        "b": (5.0, 5.0),
        "c": (7.0, 3.0),
        "d": (7.5, 7.0),
        "e": (2.5, 3.5),
    },
}

LOCATION_INDEX = {"a": 0, "b": 1, "c": 2, "d": 3, "e": 4}
INDEX_LOCATION = {v: k for k, v in LOCATION_INDEX.items()}

# Typical vitals priors per WiMANS activity (BPM).
ACTIVITY_VITALS = {
    "nothing": (12.0, 62.0),
    "walk": (18.0, 85.0),
    "rotation": (16.0, 78.0),
    "jump": (22.0, 110.0),
    "wave": (14.0, 72.0),
    "lie_down": (11.0, 58.0),
    "pick_up": (15.0, 70.0),
    "sit_down": (13.0, 65.0),
    "stand_up": (16.0, 75.0),
}


def location_to_xy(environment: str, loc: str, area_size_m: float = 10.0) -> tuple[float, float]:
    env = environment if environment in LAYOUTS else "empty_room"
    x, y = LAYOUTS[env].get(loc.lower(), (area_size_m / 2, area_size_m / 2))
    scale = area_size_m / 10.0
    return float(x * scale), float(y * scale)
