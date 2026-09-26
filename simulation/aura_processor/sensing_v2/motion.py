"""Motion detection with debounce FSM for sensing_v2.

Informed by techniques described in espressif/esp-csi (esp_wifi_sensing FSM)
and spatial-ai (baseline EMA debounce), reimplemented for ESP32 CSI in AURA.
"""

from __future__ import annotations

import numpy as np

from ..hardware_motion import esp32_motion_score, update_baseline


class MotionDebounceFSM:
    """Hysteresis + ACTIVE hold inspired by esp_wifi_sensing."""

    def __init__(self, active_hold_frames: int = 3, inactive_hold_frames: int = 2):
        self.active_hold_frames = active_hold_frames
        self.inactive_hold_frames = inactive_hold_frames
        self._state = "INACTIVE"
        self._hold = 0

    def reset(self) -> None:
        self._state = "INACTIVE"
        self._hold = 0

    def update(self, raw_motion: bool) -> bool:
        if raw_motion:
            if self._state == "INACTIVE":
                self._hold += 1
                if self._hold >= self.active_hold_frames:
                    self._state = "ACTIVE"
                    self._hold = 0
            else:
                self._hold = 0
        else:
            if self._state == "ACTIVE":
                self._hold += 1
                if self._hold >= self.inactive_hold_frames:
                    self._state = "INACTIVE"
                    self._hold = 0
            else:
                self._hold = 0
        return self._state == "ACTIVE"


def waveform_wander_jitter(csi: np.ndarray) -> dict[str, float]:
    """esp-radar inspired wander (low-freq) and jitter (high-freq) features."""
    if len(csi) < 8:
        return {"wander": 0.0, "jitter": 0.0, "stability": 0.0}

    amp = np.abs(csi).mean(axis=1)
    amp = amp - np.mean(amp)
    if len(amp) < 6:
        return {"wander": 0.0, "jitter": 0.0, "stability": 0.0}

    diff = np.diff(amp)
    wander = float(np.std(amp))
    jitter = float(np.std(diff))
    stability = float(1.0 / (1.0 + wander + jitter))
    return {"wander": wander, "jitter": jitter, "stability": stability}


def motion_score_v2(
    csi: np.ndarray,
    rssi: np.ndarray | None = None,
    baseline: float | None = None,
    motion_min: float = 0.58,
    indoor_mode: bool = False,
    debounce_frames: int = 3,
    fsm: MotionDebounceFSM | None = None,
) -> dict:
    """Enhanced motion score with wander/jitter and debounce FSM."""
    base = esp32_motion_score(csi, rssi, baseline, motion_min, indoor_mode)
    features = waveform_wander_jitter(csi)

    score = float(base["score"])
    score += 0.15 * min(features["wander"] * 2.0, 1.0)
    score += 0.10 * min(features["jitter"] * 3.0, 1.0)
    score = float(np.clip(score, 0.0, 3.5))

    threshold = float(base.get("threshold", motion_min))
    raw_motion = score >= threshold

    if fsm is None:
        fsm = MotionDebounceFSM(active_hold_frames=debounce_frames)
    debounced = fsm.update(raw_motion)

    return {
        **base,
        "score": score,
        "motion": debounced,
        "raw_motion": raw_motion,
        "wander": features["wander"],
        "jitter": features["jitter"],
        "stability": features["stability"],
        "fsm_state": "ACTIVE" if debounced else "INACTIVE",
    }


def update_motion_baseline(prev: float | None, score: float, alpha: float = 0.92) -> float:
    return update_baseline(prev, score, alpha)
