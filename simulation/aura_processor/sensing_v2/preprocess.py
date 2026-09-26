"""CSI preprocessing for sensing_v2.

Informed by techniques described in espressif/esp-csi (gain compensation)
and spatial-ai (subcarrier importance weighting), reimplemented for ESP32 CSI in AURA.
"""

from __future__ import annotations

import numpy as np

from ..hardware_csi import TARGET_SUBCARRIERS, normalize_esp32_csi


def compensate_rx_gain(csi: np.ndarray, agc_gain: float | None = None, fft_gain: float | None = None) -> np.ndarray:
    """Approximate esp_radar_compensate_rx_gain when firmware gain fields are absent."""
    out = csi.astype(np.complex128, copy=True)
    if agc_gain is not None and agc_gain > 0:
        out /= float(agc_gain)
    if fft_gain is not None and fft_gain > 0:
        out /= float(fft_gain)
    amp = np.abs(out)
    med = float(np.median(amp[amp > 0])) if np.any(amp > 0) else 1.0
    if med > 1e-9:
        out *= (1.0 / med)
    return out


def hampel_filter_1d(sig: np.ndarray, window: int = 5, n_sigmas: float = 3.0) -> np.ndarray:
    if len(sig) < window * 2 + 1:
        return sig
    out = sig.copy()
    half = window // 2
    for i in range(len(sig)):
        lo = max(0, i - half)
        hi = min(len(sig), i + half + 1)
        chunk = sig[lo:hi]
        med = float(np.median(chunk))
        mad = float(np.median(np.abs(chunk - med))) * 1.4826
        if mad > 1e-12 and abs(sig[i] - med) > n_sigmas * mad:
            out[i] = med
    return out


def subcarrier_weights(csi: np.ndarray) -> np.ndarray:
    """Per-subcarrier weights from temporal phase variance (spatial-ai technique)."""
    phase = np.angle(csi)
    if len(phase) < 4:
        return np.ones(csi.shape[1], dtype=float)
    var = np.var(np.diff(phase, axis=0), axis=0)
    var = np.maximum(var, 1e-12)
    w = var / np.sum(var)
    return w.astype(float)


def apply_subcarrier_weights(csi: np.ndarray, weights: np.ndarray) -> np.ndarray:
    w = weights.reshape(1, -1)
    return csi * w


def preprocess_csi_v2(
    csi: np.ndarray,
    *,
    gain_compensation: bool = True,
    subcarrier_weighting: bool = True,
    hampel: bool = True,
    agc_gain: float | None = None,
    fft_gain: float | None = None,
) -> tuple[np.ndarray, dict]:
    """Full v2 preprocess pipeline returning CSI and metadata."""
    csi = normalize_esp32_csi(csi)
    meta: dict = {"weights": None, "gain_compensated": False}

    if gain_compensation:
        csi = compensate_rx_gain(csi, agc_gain, fft_gain)
        meta["gain_compensated"] = True

    if hampel and len(csi) >= 12:
        amp = np.abs(csi)
        for sc in range(amp.shape[1]):
            amp[:, sc] = hampel_filter_1d(amp[:, sc])
        phase = np.angle(csi)
        csi = amp * np.exp(1j * phase)

    weights = subcarrier_weights(csi)
    meta["weights"] = weights
    if subcarrier_weighting:
        csi = apply_subcarrier_weights(csi, weights)

    return csi, meta
