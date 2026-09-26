"""Ensemble vitals extraction for sensing_v2.

Informed by techniques described in wifi-densepose-mat (DetectionPipeline ensemble)
and spatial-ai (Goertzel breathing), reimplemented for ESP32 CSI in AURA.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import welch

from ..vitals import bandpass, extract_vitals, select_vital_subcarriers
from .types import VitalsEstimate


def _goertzel_power(sig: np.ndarray, fs: float, freq: float) -> float:
    if len(sig) < 8:
        return 0.0
    n = len(sig)
    k = int(0.5 + n * freq / fs)
    w = 2.0 * np.pi * k / n
    coeff = 2.0 * np.cos(w)
    s0 = s1 = s2 = 0.0
    for x in sig:
        s0 = x + coeff * s1 - s2
        s2, s1 = s1, s0
    return float(s1 * s1 + s2 * s2 - coeff * s1 * s2)


def _goertzel_resp_bpm(sig: np.ndarray, fs: float) -> float:
    freqs = np.linspace(0.1, 0.5, 9)
    powers = [_goertzel_power(sig, fs, f) for f in freqs]
    if max(powers) < 1e-12:
        return 0.0
    best_f = freqs[int(np.argmax(powers))]
    return float(best_f * 60.0)


def _psd_peak_bpm(sig: np.ndarray, fs: float, low: float, high: float) -> float:
    if len(sig) < 16:
        return 0.0
    f, p = welch(sig, fs=fs, nperseg=min(len(sig), 64))
    mask = (f >= low) & (f <= high)
    if not np.any(mask):
        return 0.0
    peak = f[mask][np.argmax(p[mask])]
    return float(peak * 60.0)


def _pca_periodicity_bpm(csi: np.ndarray, fs: float) -> float:
    if len(csi) < 12:
        return 0.0
    phase = np.unwrap(np.angle(csi), axis=1)
    phase = phase - phase.mean(axis=0)
    try:
        u, s, _ = np.linalg.svd(phase, full_matrices=False)
        pc = u[:, 0] * s[0]
        rw = bandpass(pc, fs, 0.1, 0.55)
        return _psd_peak_bpm(rw, fs, 0.08, 0.65)
    except np.linalg.LinAlgError:
        return 0.0


def _movement_periodicity(sig: np.ndarray) -> float:
    if len(sig) < 20:
        return 0.0
    sig = sig - np.mean(sig)
    ac = np.correlate(sig, sig, mode="full")
    ac = ac[len(ac) // 2 :]
    if len(ac) < 10:
        return 0.0
    ac = ac / (ac[0] + 1e-12)
    # High periodicity in motion band suggests walking, not respiration
    return float(np.max(ac[3 : min(len(ac), 40)]))


def _signal_quality(csi: np.ndarray, stability: float = 0.5) -> float:
    if len(csi) < 8:
        return 0.0
    snr = float(np.mean(np.abs(csi))) / (float(np.std(np.abs(csi))) + 1e-9)
    snr_n = float(np.clip(snr / 10.0, 0.0, 1.0))
    return float(np.clip(0.5 * snr_n + 0.5 * stability, 0.0, 1.0))


def extract_vitals_ensemble(
    csi: np.ndarray,
    fs_hz: float,
    motion_stability: float = 0.5,
    velocity_mps: float = 0.0,
) -> VitalsEstimate:
    """Combine multiple estimators with weighted median and confidence."""
    if len(csi) < 16:
        return VitalsEstimate()

    quality = _signal_quality(csi, motion_stability)
    base = extract_vitals(csi, fs_hz, motion_cutoff_hz=1.2)

    indices = select_vital_subcarriers(csi, n=min(5, csi.shape[1]))
    goertzel_bpms: list[float] = []
    for sc in indices[:3]:
        phase = np.unwrap(np.angle(csi[:, sc]))
        rw = bandpass(phase, fs_hz, 0.1, 0.55)
        bpm = _goertzel_resp_bpm(rw, fs_hz)
        if 6 <= bpm <= 40:
            goertzel_bpms.append(bpm)

    e1 = float(np.median(goertzel_bpms)) if goertzel_bpms else 0.0
    e2 = float(base.get("respiration_bpm", 0) or 0)
    e3 = _pca_periodicity_bpm(csi, fs_hz)

    resp_estimates = [(e1, 0.9), (e2, 1.0), (e3, 0.85)]
    resp_estimates = [(b, w) for b, w in resp_estimates if 6 <= b <= 40]
    if resp_estimates:
        vals, wts = zip(*resp_estimates)
        resp_bpm = float(np.average(vals, weights=wts))
        agreement = 1.0 - min(np.std(vals) / 8.0, 1.0) if len(vals) > 1 else 0.7
        resp_conf = float(np.clip(quality * agreement, 0.0, 1.0))
    else:
        resp_bpm = 0.0
        resp_conf = 0.0

    # Heartbeat — low confidence unless still
    hr_bpm = 0.0
    hr_conf = 0.0
    still = velocity_mps < 0.15
    if still and len(csi) >= 40:
        hr_band_energy = 0.0
        for sc in indices[:2]:
            phase = np.unwrap(np.angle(csi[:, sc]))
            hw = bandpass(phase, fs_hz, 0.7, 2.0)
            hr_band_energy += float(np.var(hw))
        motion_period = _movement_periodicity(np.abs(csi).mean(axis=1))
        if hr_band_energy > 1e-6 and motion_period < 0.35:
            hr_bpm = float(base.get("heartbeat_bpm", 0) or 0)
            if 40 <= hr_bpm <= 140:
                hr_conf = float(np.clip(quality * 0.45, 0.0, 0.55))
            else:
                hr_bpm = 0.0

    return VitalsEstimate(
        resp_bpm=resp_bpm,
        hr_bpm=hr_bpm,
        resp_confidence=resp_conf,
        hr_confidence=hr_conf,
        quality=quality,
        respiration_waveform=base.get("respiration_waveform"),
        heartbeat_waveform=base.get("heartbeat_waveform"),
    )
