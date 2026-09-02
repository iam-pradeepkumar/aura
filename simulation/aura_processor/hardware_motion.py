"""Motion metrics tuned for live ESP32 CSI (amplitude + RSSI dynamics)."""

from __future__ import annotations

import numpy as np

from .hardware_csi import normalize_esp32_csi
from .multitarget import preprocess_csi
from .srcc import motion_energy, srcc


def esp32_motion_score(
    csi: np.ndarray,
    rssi: np.ndarray | None = None,
    baseline: float | None = None,
) -> dict:
    """
    Robust motion score for outdoor ESP32 CSI.

    Uses amplitude temporal variance, SRCC motion energy, and RSSI jitter.
    Returns score in ~0–3 range; values above ~1.2 usually indicate a person moving.
    """
    csi = normalize_esp32_csi(csi)
    if csi.shape[0] < 8:
        return {"score": 0.0, "motion": False, "energy": 0.0, "rssi_jitter": 0.0}

    amp = np.abs(csi)
    amp_mean = float(np.mean(amp)) + 1e-6
    temporal_var = float(np.mean(np.var(amp, axis=1)))
    amp_cv = float(np.std(amp) / amp_mean)
    ph = np.angle(csi)
    ph_diff = np.diff(ph, axis=0) if ph.shape[0] > 1 else np.zeros((1, ph.shape[1]))
    phase_var = float(np.mean(np.var(ph_diff, axis=1)))

    cleaned = np.nan_to_num(srcc(preprocess_csi(csi)))
    srcc_energy = float(np.mean(motion_energy(cleaned)))

    rssi_jitter = 0.0
    if rssi is not None and len(rssi) > 3:
        rssi_jitter = float(np.std(rssi))

    # Weighted combination — scale-invariant for int8 ESP32 amplitudes
    score = (
        0.35 * min(srcc_energy / 1.5, 2.0)
        + 0.30 * min(temporal_var / 40.0, 2.0)
        + 0.20 * min(amp_cv / 0.15, 2.0)
        + 0.10 * min(phase_var / 0.5, 2.0)
        + 0.05 * min(rssi_jitter / 2.0, 2.0)
    )

    ref = baseline if baseline and baseline > 0.05 else max(score * 0.55, 0.25)
    motion = score > max(ref * 1.35, 0.45)

    return {
        "score": float(score),
        "motion": bool(motion),
        "energy": srcc_energy,
        "temporal_var": temporal_var,
        "rssi_jitter": rssi_jitter,
        "baseline": float(ref),
    }


def update_baseline(prev: float | None, score: float, alpha: float = 0.92) -> float:
    """EMA noise floor — adapts when scene is quiet."""
    if prev is None or prev <= 0:
        return float(score)
    if score < prev * 1.15:
        return alpha * prev + (1 - alpha) * score
    return prev
