"""Convert sensing results to JSON-safe dicts for the web dashboard."""

from __future__ import annotations

import numpy as np

from .pipeline import SensingResult
from .localization import Target


def target_to_dict(t: Target) -> dict:
    out = {
        "id": t.id,
        "x_m": round(t.x_m, 3),
        "y_m": round(t.y_m, 3),
        "velocity_mps": round(t.velocity_mps, 3),
        "acceleration_mps2": round(t.acceleration_mps2, 3),
        "is_moving": t.is_moving,
        "respiration_bpm": round(t.respiration_bpm, 1),
        "heartbeat_bpm": round(t.heartbeat_bpm, 1),
        "trajectory": [(round(x, 3), round(y, 3)) for x, y in t.trajectory[-40:]],
    }
    if t.respiration_waveform is not None and len(t.respiration_waveform):
        out["respiration_waveform"] = _downsample(t.respiration_waveform)
    else:
        out["respiration_waveform"] = []
    if t.heartbeat_waveform is not None and len(t.heartbeat_waveform):
        out["heartbeat_waveform"] = _downsample(t.heartbeat_waveform)
    else:
        out["heartbeat_waveform"] = []
    return out


def result_to_dict(res: SensingResult, include_waveforms: bool = True) -> dict:
    out = {
        "timestamp_sec": round(res.timestamp_sec, 3),
        "motion_detected": res.motion_detected,
        "motion_energy": round(res.motion_energy, 5),
        "target_count": res.target_count,
        "confidence": round(getattr(res, "confidence", 0.0), 3),
        "respiration_bpm": round(res.respiration_bpm, 1),
        "heartbeat_bpm": round(res.heartbeat_bpm, 1),
        "targets": [target_to_dict(t) for t in res.targets],
        "events": res.events[-5:],
    }
    if include_waveforms:
        out["respiration_waveform"] = []
        out["heartbeat_waveform"] = []
        # Per-person waveforms live on each target; aggregate charts use targets[]
    return out


def _downsample(arr: np.ndarray, max_pts: int = 80) -> list[float]:
    if arr is None or len(arr) == 0:
        return []
    if len(arr) <= max_pts:
        return [round(float(v), 5) for v in arr]
    idx = np.linspace(0, len(arr) - 1, max_pts, dtype=int)
    return [round(float(arr[i]), 5) for i in idx]
