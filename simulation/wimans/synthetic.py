"""Synthetic WiMANS-style amplitude CSI for bootstrap training."""

from __future__ import annotations

import numpy as np

from .layouts import LOCATION_INDEX

ACTIVITY_FREQ = {
    "nothing": 0.15,
    "walk": 1.8,
    "rotation": 1.2,
    "jump": 2.5,
    "wave": 1.0,
    "lie_down": 0.25,
    "pick_up": 0.9,
    "sit_down": 0.6,
    "stand_up": 0.8,
}


def synth_amplitude(
    n_users: int,
    locations: list[str],
    activities: list[str],
    seed: int,
    frames: int = 3000,
    n_sc: int = 30,
) -> np.ndarray:
    """Generate amplitude CSI with distinct per-user motion signatures."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, frames / 1000.0, frames)
    amp = np.zeros((frames, n_sc), dtype=np.float64)

    for i in range(min(n_users, len(locations), len(activities))):
        loc = locations[i].lower()
        act = activities[i].lower() if i < len(activities) else "walk"
        freq = ACTIVITY_FREQ.get(act, 1.0) * (0.85 + 0.3 * rng.random())
        loc_idx = LOCATION_INDEX.get(loc, i % 5)
        sc_center = int(3 + loc_idx * 5 + rng.integers(-1, 2))
        sc_lo = max(0, sc_center - 4)
        sc_hi = min(n_sc, sc_center + 5)
        phase = 2 * np.pi * freq * t + rng.uniform(0, 2 * np.pi)
        envelope = 0.55 + 0.45 * np.sin(2 * np.pi * (0.2 + 0.1 * i) * t + rng.uniform(0, 1))
        for sc in range(sc_lo, sc_hi):
            amp[:, sc] += envelope * (0.7 + 0.3 * np.sin(phase + sc * 0.08 + i * 0.4))
        amp[:, sc_lo:sc_hi] += rng.normal(0, 0.04, (frames, sc_hi - sc_lo))

    amp += rng.normal(0, 0.03, amp.shape)
    amp = np.abs(amp)
    return amp.astype(np.float32)
