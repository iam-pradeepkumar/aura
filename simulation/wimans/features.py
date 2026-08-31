"""Feature extraction from WiMANS-style CSI amplitude (T × 30)."""

from __future__ import annotations

import numpy as np
from scipy.signal import detrend, stft

TARGET_FRAMES = 3000
TARGET_SC = 30


def pad_amplitude(amp: np.ndarray, frames: int = TARGET_FRAMES, sc: int = TARGET_SC) -> np.ndarray:
    """Pad/truncate amplitude to (frames, subcarriers)."""
    a = np.asarray(amp, dtype=np.float64)
    if a.ndim == 1:
        a = a.reshape(1, -1)
    if a.ndim > 2:
        a = a.reshape(a.shape[0], -1)
    if a.shape[1] > sc:
        a = a[:, :sc]
    elif a.shape[1] < sc:
        a = np.pad(a, ((0, 0), (0, sc - a.shape[1])), mode="edge")
    if a.shape[0] > frames:
        a = a[-frames:]
    elif a.shape[0] < frames:
        pad = frames - a.shape[0]
        a = np.pad(a, ((pad, 0), (0, 0)), mode="edge")
    med = float(np.median(a))
    scale = float(np.median(np.abs(a - med))) + 1e-6
    return (a - med) / scale


def flatten_amplitude(amp: np.ndarray) -> np.ndarray:
    return pad_amplitude(amp).reshape(-1).astype(np.float32)


def extract_features(amp: np.ndarray, fs_hz: float = 1000.0) -> np.ndarray:
    """Compact, transferable features for WiMANS-trained models."""
    a = pad_amplitude(amp)
    t_len, n_sc = a.shape
    feats: list[float] = []

    diff = np.diff(a, axis=0)
    feats.extend(np.var(diff, axis=0).tolist())
    feats.extend(np.mean(np.abs(diff), axis=0).tolist())

    row_var = np.var(a, axis=1)
    feats.append(float(np.mean(row_var)))
    feats.append(float(np.std(row_var)))
    feats.append(float(np.max(row_var)))
    feats.append(float(np.percentile(row_var, 90)))

    try:
        _, s, _ = np.linalg.svd(a - a.mean(axis=0), full_matrices=False)
        feats.extend((s[:12] / (s[0] + 1e-9)).tolist())
    except np.linalg.LinAlgError:
        feats.extend([0.0] * 12)

    nperseg = min(256, max(64, t_len // 8))
    f, t, zxx = stft(a.mean(axis=1), fs=fs_hz, nperseg=nperseg, noverlap=nperseg // 2)
    power = np.abs(zxx) ** 2
    for lo, hi in ((0.1, 0.5), (0.5, 2.0), (2.0, 5.0), (5.0, 15.0)):
        mask = (f >= lo) & (f < hi)
        feats.append(float(power[mask].sum()) if mask.any() else 0.0)

    corr = np.corrcoef(a.T)
    corr = np.nan_to_num(corr)
    off = corr[np.triu_indices(n_sc, k=1)]
    feats.append(float(np.mean(off)))
    feats.append(float(np.std(off)))
    feats.append(float(np.percentile(off, 95)))

    return np.asarray(feats, dtype=np.float32)
