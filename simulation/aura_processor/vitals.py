"""Vital sign extraction: respiration and heartbeat from CSI phase."""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt, welch, detrend
from scipy.ndimage import uniform_filter1d


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
        base = uniform_filter1d(sig.astype(float), size=max(3, int(fs * 0.5)), mode="nearest")
        return sig - base
    return filtfilt(b, a, sig)


def select_vital_subcarriers(csi: np.ndarray, n: int = 5) -> list[int]:
    phase = np.angle(csi)
    var = np.var(np.diff(phase, axis=0), axis=0)
    return np.argsort(var)[-n:].tolist()


def _decimate_for_vitals(csi: np.ndarray, fs_hz: float, target_fs: float = 25.0) -> tuple[np.ndarray, float]:
    """Downsample high-rate CSI so respiration/heartbeat bandpass filters are stable."""
    if fs_hz <= target_fs * 1.5 or len(csi) < 16:
        return csi, fs_hz
    factor = max(int(fs_hz / target_fs), 2)
    return csi[::factor], fs_hz / factor


def extract_vitals(csi: np.ndarray, fs_hz: float, motion_cutoff_hz: float = 2.5) -> dict:
    """
    Extract respiration and heartbeat. For jumping targets, vitals are taken from
    the low-frequency component after suppressing jump motion (>2.5 Hz).
    """
    if len(csi) < 8:
        return _empty_vitals()

    csi, fs_hz = _decimate_for_vitals(csi, fs_hz)
    if fs_hz > 80:
        motion_cutoff_hz = min(motion_cutoff_hz, 1.2)

    indices = select_vital_subcarriers(csi, n=min(8, csi.shape[1]))
    resp_waves, hr_waves = [], []
    resp_bpms, hr_bpms = [], []

    for sc in indices:
        phase = np.unwrap(np.angle(csi[:, sc]))
        phase = detrend(phase, type="linear")
        # Remove jump / large motion before vitals
        phase_slow = bandpass(phase, fs_hz, 0.05, motion_cutoff_hz)
        rw = bandpass(phase_slow, fs_hz, 0.1, 0.55)
        hw = bandpass(phase_slow, fs_hz, 0.7, 2.0)
        rb = _bpm_from_psd(rw, fs_hz, 0.08, 0.65)
        hb = _bpm_from_psd(hw, fs_hz, 0.6, 2.2)
        if rb > 0:
            resp_bpms.append(rb)
            resp_waves.append(rw)
        if hb > 0:
            hr_bpms.append(hb)
            hr_waves.append(hw)

    # PCA on phase matrix
    phase_mat = np.unwrap(np.angle(csi), axis=1)
    phase_mat = detrend(phase_mat, axis=0, type="linear")
    try:
        U, S, _ = np.linalg.svd(phase_mat - phase_mat.mean(axis=0), full_matrices=False)
        for i in range(min(3, len(S))):
            pc = U[:, i] * S[i]
            pc_slow = bandpass(pc, fs_hz, 0.05, motion_cutoff_hz)
            rw = bandpass(pc_slow, fs_hz, 0.1, 0.55)
            hw = bandpass(pc_slow, fs_hz, 0.7, 2.0)
            rb = _bpm_from_psd(rw, fs_hz, 0.08, 0.65)
            hb = _bpm_from_psd(hw, fs_hz, 0.6, 2.2)
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

    # If respiration peak not found but heartbeat exists, estimate ~4:1 HR:RR ratio
    if resp_bpm <= 0 and hr_bpm > 0:
        resp_bpm = float(np.clip(hr_bpm / 4.0, 8.0, 30.0))

    resp_wave = np.mean(resp_waves, axis=0) if resp_waves else np.zeros(len(csi))
    hr_wave = np.mean(hr_waves, axis=0) if hr_waves else np.zeros(len(csi))

    if resp_bpm > 0 and not resp_waves:
        # Synthesize display waveform from estimated rate
        t = np.arange(len(csi)) / fs_hz
        resp_wave = 0.5 * np.sin(2 * np.pi * (resp_bpm / 60.0) * t)

    return {
        "respiration_waveform": resp_wave,
        "heartbeat_waveform": hr_wave,
        "respiration_bpm": resp_bpm,
        "heartbeat_bpm": hr_bpm,
    }


def extract_vitals_for_target(csi: np.ndarray, fs_hz: float, delay_bin: int, n_sc: int = 8) -> dict:
    n = csi.shape[1]
    lo = max(0, delay_bin - n_sc // 2)
    hi = min(n, delay_bin + n_sc // 2 + 1)
    return extract_vitals(csi[:, lo:hi], fs_hz, motion_cutoff_hz=1.5 if fs_hz < 100 else 2.5)


def _svd_phase_sources(csi: np.ndarray, n_sources: int) -> list[np.ndarray]:
    """Return per-source phase matrices from SVD decomposition."""
    phase = np.angle(csi)
    phase = detrend(phase, axis=0, type="linear")
    phase = phase - phase.mean(axis=0, keepdims=True)
    try:
        u, s, vh = np.linalg.svd(phase, full_matrices=False)
    except np.linalg.LinAlgError:
        return []
    sources = []
    for i in range(min(n_sources, len(s))):
        if s[i] < 0.05 * s[0]:
            continue
        comp = (u[:, i : i + 1] * s[i]) @ vh[i : i + 1, :]
        sources.append(comp)
    return sources


def extract_vitals_for_detections(
    csi: np.ndarray,
    fs_hz: float,
    detections: list[dict],
) -> list[dict]:
    """
    Extract isolated respiration/heartbeat for each detected person.
    Matches SVD motion sources to detections by delay_bin proximity.
    """
    if not detections:
        return []

    n_sc = csi.shape[1]
    n_targets = len(detections)
    sources = _svd_phase_sources(csi, n_targets)
    results: list[dict] = []
    used_sources: set[int] = set()

    for i, det in enumerate(detections):
        delay_bin = int(det.get("delay_bin", 0))
        src_idx = int(det.get("source_id", -1))
        best_src = None
        best_dist = 999

        if 0 <= src_idx < len(sources) and src_idx not in used_sources:
            best_src = sources[src_idx]
            best_dist = 0
        else:
            for si, comp in enumerate(sources):
                if si in used_sources:
                    continue
                prof = np.abs(np.fft.ifft(np.exp(1j * np.angle(comp)), axis=1)).mean(axis=0)
                peak = int(np.argmax(prof))
                dist = abs(peak - delay_bin)
                if dist < best_dist:
                    best_dist = dist
                    best_src = comp
                    src_idx = si

        if best_src is not None and src_idx >= 0:
            used_sources.add(src_idx)
            pseudo = np.exp(1j * np.angle(best_src))
            v = extract_vitals(pseudo, fs_hz, motion_cutoff_hz=1.35 if fs_hz < 100 else 2.0)
        else:
            band_w = max(6, n_sc // max(n_targets * 2, 4))
            offset = (i * max(4, band_w // 2)) % max(1, n_sc - band_w)
            lo = max(0, min(delay_bin - band_w // 2, n_sc - band_w) + offset // 2)
            hi = min(n_sc, lo + band_w)
            v = extract_vitals(csi[:, lo:hi], fs_hz, motion_cutoff_hz=1.35 if fs_hz < 100 else 2.0)

        results.append(v)

    return results


def _bpm_from_psd(sig: np.ndarray, fs: float, f_lo: float, f_hi: float) -> float:
    min_len = max(int(fs * 0.35), 8)
    if len(sig) < min_len:
        return 0.0
    nperseg = min(max(int(fs * 1.0), 32), len(sig))
    freqs, psd = welch(sig, fs=fs, nperseg=nperseg, noverlap=nperseg // 2)
    mask = (freqs >= f_lo) & (freqs <= f_hi)
    if not np.any(mask):
        return 0.0
    peak_idx = np.argmax(psd[mask])
    if psd[mask][peak_idx] < 1e-14:
        return 0.0
    return float(freqs[mask][peak_idx] * 60.0)


def _empty_vitals() -> dict:
    return {
        "respiration_waveform": np.array([]),
        "heartbeat_waveform": np.array([]),
        "respiration_bpm": 0.0,
        "heartbeat_bpm": 0.0,
    }
