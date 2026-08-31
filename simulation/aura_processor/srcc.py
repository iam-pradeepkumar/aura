"""Self-Referencing Cross-Correlation (SRCC) — WiDFS 3.0 adapted for ESP32 CSI."""

from __future__ import annotations

import numpy as np
from scipy.ndimage import gaussian_filter1d


def reconstruct_csi(csi_row: np.ndarray, sigma: float = 2.0) -> np.ndarray:
    """Energy-adjusted CSI via delay-domain Gaussian windowing (paper Eq. 3-6)."""
    h = np.fft.ifft(csi_row)
    power = np.abs(h) ** 2
    peak = int(np.argmax(power))
    n = len(h)
    tau = np.arange(n)
    window = np.exp(-0.5 * ((tau - peak) / max(sigma, 0.5)) ** 2)
    h_win = h * window
    return np.fft.fft(h_win)


def srcc(csi: np.ndarray) -> np.ndarray:
    """
    Apply SRCC along subcarriers per time sample.
    csi: (T, N_subcarriers) complex
  Returns cleaned CSI same shape.
    """
    out = np.zeros_like(csi, dtype=np.complex64)
    for t in range(csi.shape[0]):
        ref = reconstruct_csi(csi[t])
        out[t] = csi[t] * np.conj(ref)
        denom = np.abs(ref) + 1e-8
        out[t] /= denom
    return np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)


def amplitude(csi: np.ndarray) -> np.ndarray:
    return np.abs(csi)


def phase_unwrap(csi: np.ndarray) -> np.ndarray:
    """Unwrap phase across subcarriers for each time step."""
    ph = np.angle(csi)
    return np.unwrap(ph, axis=1)


def motion_energy(csi: np.ndarray, window: int = 32) -> np.ndarray:
    """Per-frame motion from amplitude + phase dynamics (uses full complex CSI)."""
    amp = amplitude(csi)
    amp_var = np.var(amp, axis=1)
    ph = np.angle(csi)
    if ph.shape[0] > 1:
        ph_diff = np.diff(ph, axis=0, prepend=ph[:1])
        phase_var = np.var(ph_diff, axis=1)
    else:
        phase_var = np.zeros(len(amp_var))
    combined = amp_var + 0.45 * phase_var
    if window > 1:
        return gaussian_filter1d(combined, sigma=window / 6.0)
    return combined
