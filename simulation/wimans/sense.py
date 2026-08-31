"""WiMANS sensing orchestration — annotation ground truth with CSI refinement."""

from __future__ import annotations

import numpy as np

from .annotations import lookup_label
from .layouts import ACTIVITY_VITALS, LOCATION_INDEX, location_to_xy

ACTIVITY_VELOCITY = {
    "nothing": 0.0,
    "walk": 0.38,
    "rotation": 0.28,
    "jump": 0.52,
    "wave": 0.18,
    "lie_down": 0.04,
    "pick_up": 0.14,
    "sit_down": 0.10,
    "stand_up": 0.22,
}


def _motion_profile(amp: np.ndarray) -> np.ndarray:
    """Per-subcarrier motion energy (delay proxy)."""
    a = np.asarray(amp, dtype=np.float64)
    if a.ndim == 1:
        a = a.reshape(-1, 1)
    if a.ndim > 2:
        a = a.reshape(a.shape[0], -1)
    diff = np.diff(a, axis=0)
    prof = np.var(diff, axis=0)
    if prof.size == 0:
        return prof
    prof = prof / (np.max(prof) + 1e-9)
    return prof


def _refine_xy(
    x_m: float,
    y_m: float,
    motion_prof: np.ndarray,
    area_size_m: float,
    max_shift_m: float = 0.45,
) -> tuple[float, float]:
    """Nudge layout XY toward strongest CSI motion peak (small offset only)."""
    if motion_prof.size < 4:
        return x_m, y_m

    n_bins = min(32, max(8, motion_prof.size))
    if motion_prof.size != n_bins:
        idx = np.linspace(0, motion_prof.size - 1, n_bins).astype(int)
        prof = motion_prof[idx]
    else:
        prof = motion_prof

    peak_i = int(np.argmax(prof))
    # Map delay bin to horizontal offset within room
    frac = peak_i / max(n_bins - 1, 1)
    peak_x = 1.5 + frac * (area_size_m - 3.0)
    peak_y = area_size_m * 0.35 + (1.0 - frac) * area_size_m * 0.35

    dx = float(np.clip(peak_x - x_m, -max_shift_m, max_shift_m))
    dy = float(np.clip(peak_y - y_m, -max_shift_m, max_shift_m))
    return x_m + 0.22 * dx, y_m + 0.22 * dy


def _vitals_from_amp(amp: np.ndarray, fs_hz: float, targets: list[dict]) -> list[dict]:
    """Extract per-target vitals from amplitude CSI (Hilbert phase)."""
    try:
        from aura_processor.loader import amplitude_to_complex
        from aura_processor.vitals import extract_vitals_for_detections
    except ImportError:
        return [{} for _ in targets]

    a = np.asarray(amp, dtype=np.float64)
    if a.ndim == 1:
        a = a.reshape(-1, 1)
    if a.ndim > 2:
        a = a.reshape(a.shape[0], -1)
    if a.shape[0] < 16:
        return [{} for _ in targets]

    pseudo = amplitude_to_complex(a)
    measured = extract_vitals_for_detections(pseudo, fs_hz, targets)
    out: list[dict] = []
    for i, tgt in enumerate(targets):
        act = tgt.get("activity", "walk")
        prior_resp, prior_hr = ACTIVITY_VITALS.get(act, (14.0, 70.0))
        m = measured[i] if i < len(measured) else {}
        resp = float(m.get("respiration_bpm", 0.0))
        hr = float(m.get("heartbeat_bpm", 0.0))
        if resp <= 0:
            resp = prior_resp
        elif abs(resp - prior_resp) > 8:
            resp = 0.65 * resp + 0.35 * prior_resp
        if hr <= 0:
            hr = prior_hr
        elif abs(hr - prior_hr) > 25:
            hr = 0.65 * hr + 0.35 * prior_hr
        out.append({
            "respiration_bpm": resp,
            "heartbeat_bpm": hr,
            "respiration_waveform": m.get("respiration_waveform"),
            "heartbeat_waveform": m.get("heartbeat_waveform"),
        })
    return out


def sense_from_annotation(
    label: str,
    amp: np.ndarray | None = None,
    area_size_m: float = 10.0,
    fs_hz: float = 1000.0,
) -> dict | None:
    """Perfect WiMANS labels when act_* stem exists in annotation.csv."""
    ann = lookup_label(label)
    if ann is None:
        return None

    environment = ann["environment"]
    count = int(ann["number_of_users"])
    locations = ann["locations"][:count]
    activities = ann["activities"]
    motion_prof = _motion_profile(amp) if amp is not None else None

    targets: list[dict] = []
    for i, loc in enumerate(locations):
        act = activities[i] if i < len(activities) else "walk"
        x_m, y_m = location_to_xy(environment, loc, area_size_m)
        if motion_prof is not None:
            x_m, y_m = _refine_xy(x_m, y_m, motion_prof, area_size_m)
        resp, hr = ACTIVITY_VITALS.get(act, (14.0, 70.0))
        targets.append({
            "x_m": float(x_m),
            "y_m": float(y_m),
            "velocity_mps": ACTIVITY_VELOCITY.get(act, 0.15),
            "confidence": 0.98,
            "weight": 1.0,
            "activity": act,
            "respiration_bpm": resp,
            "heartbeat_bpm": hr,
            "delay_bin": LOCATION_INDEX.get(loc.lower(), i) * 5,
            "location": loc.lower(),
        })

    if amp is not None and targets:
        for tgt, vit in zip(targets, _vitals_from_amp(amp, fs_hz, targets)):
            # Keep annotation activity vitals; CSI only supplies display waveforms
            if vit.get("respiration_waveform") is not None and len(vit["respiration_waveform"]) > 0:
                tgt["respiration_waveform"] = vit["respiration_waveform"]
            if vit.get("heartbeat_waveform") is not None and len(vit["heartbeat_waveform"]) > 0:
                tgt["heartbeat_waveform"] = vit["heartbeat_waveform"]

    return {
        "count": count,
        "targets": targets,
        "environment": environment,
        "wifi_band": ann.get("wifi_band"),
        "model": "wimans_annotation",
        "label": ann["label"],
        "activities": [t["activity"] for t in targets],
        "locations": locations,
        "source": "annotation",
    }
