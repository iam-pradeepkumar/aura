"""Delay-Doppler feature extraction for localization and tracking."""

from __future__ import annotations

import numpy as np
from scipy.signal import stft, find_peaks


def delay_doppler_map(
    csi: np.ndarray,
    fs_hz: float,
    n_fft_time: int | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Build delay-Doppler spectrogram from cleaned CSI.
    Uses mean amplitude across subcarriers as SISO proxy (ESP32 single antenna).
    """
    sig = np.mean(np.abs(csi), axis=1)
    sig = sig - np.mean(sig)
    nperseg = min(64, max(16, len(sig) // 4))
    if n_fft_time:
        nperseg = min(nperseg, n_fft_time)
    f, t, zxx = stft(sig, fs=fs_hz, nperseg=nperseg, noverlap=nperseg // 2)
    return f, t, np.abs(zxx)


def estimate_doppler_velocity(doppler_hz: float, carrier_ghz: float = 2.4) -> float:
    """Radial velocity from Doppler shift (m/s)."""
    c = 299_792_458.0
    fc = carrier_ghz * 1e9
    return doppler_hz * c / (2.0 * fc)


def range_from_delay(delay_s: float) -> float:
    """Bistatic range from time delay (m)."""
    c = 299_792_458.0
    return delay_s * c


def extract_motion_parameters(
    csi: np.ndarray,
    fs_hz: float,
    area_size_m: float = 10.0,
) -> dict:
    """Estimate Doppler, coarse range, XY from SISO link (single RX node)."""
    f, t, ddm = delay_doppler_map(csi, fs_hz)
    power = ddm ** 2
    idx = np.unravel_index(np.argmax(power), power.shape)
    doppler_hz = float(f[idx[0]])
    delay_idx = idx[1]
    delay_s = delay_idx / fs_hz if fs_hz > 0 else 0.0
    rng = min(range_from_delay(delay_s), area_size_m)

    # Map radial to XY (polar → Cartesian, angle from subcarrier phase slope)
    phase = np.angle(np.mean(csi, axis=0))
    slope = np.polyfit(np.arange(len(phase)), np.unwrap(phase), 1)[0]
    angle_rad = np.clip(slope * 0.15, -np.pi / 2, np.pi / 2)
    x = rng * np.cos(angle_rad)
    y = rng * np.sin(angle_rad)
    vel = estimate_doppler_velocity(doppler_hz)

    return {
        "doppler_hz": doppler_hz,
        "range_m": rng,
        "x_m": float(x),
        "y_m": float(y),
        "velocity_mps": float(vel),
        "delay_doppler_map": ddm,
        "doppler_axis": f,
        "time_axis": t,
    }


def detect_peaks_multi_target(ddm: np.ndarray, max_targets: int = 4) -> list[tuple[int, int, float]]:
    """Find multiple delay-Doppler peaks for people counting."""
    flat = ddm.ravel()
    if flat.max() <= 0:
        return []
    thresh = 0.35 * flat.max()
    peaks, props = find_peaks(flat, height=thresh, distance=max(3, len(flat) // 50))
    scored = sorted(zip(peaks, props["peak_heights"]), key=lambda x: -x[1])
    results = []
    ny, nx = ddm.shape
    for peak_idx, height in scored[:max_targets]:
        di, ti = divmod(int(peak_idx), nx)
        results.append((di, ti, float(height)))
    return results
