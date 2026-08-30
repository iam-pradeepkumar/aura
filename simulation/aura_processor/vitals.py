"""Vital sign extraction: respiration and heartbeat from CSI phase."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt, welch, detrend


def bandpass(sig: np.ndarray, fs: float, low: float, high: float, order: int = 4) -> np.ndarray:
    if len(sig) < order * 6:
        return sig - np.mean(sig)
    nyq = 0.5 * fs
    low_n = max(low / nyq, 1e-4)
    high_n = min(high / nyq, 0.99)
    if low_n >= high_n:
        return sig
    b, a = butter(order, [low_n, high_n], btype="band")
    padlen = 3 * max(len(a), len(b))
    if len(sig) <= padlen:
        return sig - np.mean(sig)
    return filtfilt(b, a, sig)


def select_vital_subcarrier(csi: np.ndarray) -> np.ndarray:
    """Pick subcarrier with highest phase variance (motion-sensitive)."""
    phase = np.angle(csi)
    var = np.var(np.diff(phase, axis=0), axis=0)
    idx = int(np.argmax(var))
    return np.unwrap(phase[:, idx])


def extract_vitals(
    csi: np.ndarray,
    fs_hz: float,
) -> dict:
    """
    Extract respiration and heartbeat waveforms and BPM estimates.
    Reference at rest: resp ~11/min (0.18 Hz), HR ~65/min (1.08 Hz).
    """
    phase = select_vital_subcarrier(csi)
    phase = detrend(phase, type="linear")

    resp_wave = bandpass(phase, fs_hz, 0.1, 0.5)
    hr_wave = bandpass(phase, fs_hz, 0.8, 2.0)

    resp_bpm = _bpm_from_psd(resp_wave, fs_hz, 0.08, 0.6)
    hr_bpm = _bpm_from_psd(hr_wave, fs_hz, 0.7, 2.5)

    return {
        "respiration_waveform": resp_wave,
        "heartbeat_waveform": hr_wave,
        "respiration_bpm": resp_bpm,
        "heartbeat_bpm": hr_bpm,
    }


def _bpm_from_psd(sig: np.ndarray, fs: float, f_lo: float, f_hi: float) -> float:
    if len(sig) < int(fs * 2):
        return 0.0
    freqs, psd = welch(sig, fs=fs, nperseg=min(256, len(sig)))
    mask = (freqs >= f_lo) & (freqs <= f_hi)
    if not np.any(mask):
        return 0.0
    peak_f = freqs[mask][np.argmax(psd[mask])]
    return float(peak_f * 60.0)
