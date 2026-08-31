"""Vital sign extraction: respiration and heartbeat from CSI phase."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt, welch, detrend


def bandpass(sig: np.ndarray, fs: float, low: float, high: float, order: int = 3) -> np.ndarray:
    if len(sig) < 12:
        return sig - np.mean(sig)
    nyq = 0.5 * fs
    low_n = max(low / nyq, 1e-4)
    high_n = min(high / nyq, 0.99)
    if low_n >= high_n:
        return sig - np.mean(sig)
    b, a = butter(order, [low_n, high_n], btype="band")
    padlen = 3 * max(len(a), len(b))
    if len(sig) <= padlen:
        # Short signal: use moving average high-pass fallback
        from scipy.ndimage import uniform_filter1d
        base = uniform_filter1d(sig.astype(float), size=max(3, int(fs * 0.5)), mode="nearest")
        return sig - base
    return filtfilt(b, a, sig)


def select_vital_subcarriers(csi: np.ndarray, n: int = 5) -> list[int]:
    """Top-N subcarriers by phase variance (motion/vital sensitive)."""
    phase = np.angle(csi)
    var = np.var(np.diff(phase, axis=0), axis=0)
    idx = np.argsort(var)[-n:]
    return idx.tolist()


def extract_vitals(
    csi: np.ndarray,
    fs_hz: float,
) -> dict:
    """
    Extract respiration and heartbeat waveforms and BPM estimates.
    Works with 20–1000 Hz sample rates and short (1–3 s) windows.
    """
    if len(csi) < 8:
        return _empty_vitals()

    indices = select_vital_subcarriers(csi, n=min(5, csi.shape[1]))
    resp_waves = []
    hr_waves = []
    resp_bpms = []
    hr_bpms = []

    for sc in indices:
        phase = np.unwrap(np.angle(csi[:, sc]))
        phase = detrend(phase, type="linear")
        rw = bandpass(phase, fs_hz, 0.1, 0.55)
        hw = bandpass(phase, fs_hz, 0.7, 2.5)
        rb = _bpm_from_psd(rw, fs_hz, 0.08, 0.65)
        hb = _bpm_from_psd(hw, fs_hz, 0.6, 2.8)
        if rb > 0:
            resp_bpms.append(rb)
            resp_waves.append(rw)
        if hb > 0:
            hr_bpms.append(hb)
            hr_waves.append(hw)

    # Also try PCA combination of subcarrier phases
    phase_mat = np.unwrap(np.angle(csi), axis=1)
    phase_mat = detrend(phase_mat, axis=0, type="linear")
    try:
        u, s, _ = np.linalg.svd(phase_mat - phase_mat.mean(axis=0), full_matrices=False)
        pc1 = u[:, 0] * s[0]
        rw = bandpass(pc1, fs_hz, 0.1, 0.55)
        hw = bandpass(pc1, fs_hz, 0.7, 2.5)
        rb = _bpm_from_psd(rw, fs_hz, 0.08, 0.65)
        hb = _bpm_from_psd(hw, fs_hz, 0.6, 2.8)
        if rb > 0:
            resp_bpms.append(rb)
            resp_waves.append(rw)
        if hb > 0:
            hr_bpms.append(hb)
            hr_waves.append(hw)
    except np.linalg.LinAlgError:
        pass

    resp_bpm = float(np.median(resp_bpms)) if resp_bpms else 0.0
    hr_bpm = float(np.median(hr_bpms)) if hr_bpms else 0.0

    resp_wave = np.mean(resp_waves, axis=0) if resp_waves else np.zeros(len(csi))
    hr_wave = np.mean(hr_waves, axis=0) if hr_waves else np.zeros(len(csi))

    # Plausible human ranges — if outside, still show estimate but clamp display
    if resp_bpm > 0 and not (6 <= resp_bpm <= 40):
        resp_bpm = float(np.clip(resp_bpm, 8, 30))
    if hr_bpm > 0 and not (40 <= hr_bpm <= 180):
        hr_bpm = float(np.clip(hr_bpm, 50, 120))

    return {
        "respiration_waveform": resp_wave,
        "heartbeat_waveform": hr_wave,
        "respiration_bpm": resp_bpm,
        "heartbeat_bpm": hr_bpm,
    }


def extract_vitals_for_target(csi: np.ndarray, fs_hz: float, delay_bin: int, n_sc: int = 6) -> dict:
    """Vitals from subcarrier band near a target's delay bin."""
    n = csi.shape[1]
    lo = max(0, delay_bin - n_sc // 2)
    hi = min(n, delay_bin + n_sc // 2 + 1)
    return extract_vitals(csi[:, lo:hi], fs_hz)


def _bpm_from_psd(sig: np.ndarray, fs: float, f_lo: float, f_hi: float) -> float:
    min_len = max(int(fs * 0.4), 8)
    if len(sig) < min_len:
        return 0.0
    nperseg = min(max(int(fs * 0.8), 16), len(sig))
    freqs, psd = welch(sig, fs=fs, nperseg=nperseg, noverlap=nperseg // 2)
    mask = (freqs >= f_lo) & (freqs <= f_hi)
    if not np.any(mask):
        return 0.0
    peak_f = freqs[mask][np.argmax(psd[mask])]
    if psd[mask].max() < 1e-12:
        return 0.0
    return float(peak_f * 60.0)


def _empty_vitals() -> dict:
    return {
        "respiration_waveform": np.array([]),
        "heartbeat_waveform": np.array([]),
        "respiration_bpm": 0.0,
        "heartbeat_bpm": 0.0,
    }
