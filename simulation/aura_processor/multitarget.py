"""Multi-target detection, clustering, and XY localization from CSI."""

from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks, stft

from .srcc import srcc


def trim_csi_to_video(
    csi: np.ndarray,
    timestamps_ms: np.ndarray,
    video_duration_sec: float,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Keep only CSI samples that match the video clip duration."""
    n = len(csi)
    if n == 0:
        return csi, timestamps_ms, 20.0

    if len(timestamps_ms) > 1:
        t0 = float(timestamps_ms[0])
        span_sec = (float(timestamps_ms[-1]) - t0) / 1000.0
        if span_sec > video_duration_sec * 1.2:
            # CSI file longer than video — take first segment matching video length
            mask = (timestamps_ms - t0) <= video_duration_sec * 1000.0 + 1.0
            csi = csi[mask]
            timestamps_ms = timestamps_ms[mask] - t0
        else:
            timestamps_ms = timestamps_ms - t0
        fs = (len(csi) - 1) / max(video_duration_sec, 0.1) if len(csi) > 1 else 20.0
    else:
        # No timestamps — assume CSI matches video length exactly
        n_keep = min(n, max(int(video_duration_sec * 1000), 32))
        csi = csi[:n_keep]
        timestamps_ms = np.linspace(0, video_duration_sec * 1000, len(csi))
        fs = (len(csi) - 1) / max(video_duration_sec, 0.1)

    fs = float(np.clip(fs, 10.0, 2000.0))
    return csi, timestamps_ms, fs


def _delay_profile(csi: np.ndarray) -> np.ndarray:
    """Mean delay-domain energy across time (per person multipath peak)."""
    h = np.abs(np.fft.ifft(csi, axis=1))
    return h.mean(axis=0)


def _subcarrier_angle(csi: np.ndarray, weights: np.ndarray | None = None) -> float:
    """Estimate horizontal angle proxy from phase slope across subcarriers."""
    phase = np.angle(csi)
    if weights is not None and len(weights) == len(csi):
        w = weights / (weights.sum() + 1e-8)
        mean_phase = np.average(phase, axis=0, weights=w)
    else:
        mean_phase = phase.mean(axis=0)
    mean_phase = np.unwrap(mean_phase)
    sc = np.arange(len(mean_phase))
    slope = np.polyfit(sc, mean_phase, 1)[0]
    return float(np.clip(slope * 2.5, -1.2, 1.2))


def _doppler_per_target(csi: np.ndarray, fs_hz: float) -> np.ndarray:
    """Per-subcarrier mean Doppler energy for segmentation."""
    sig = np.abs(csi)
    sig = sig - sig.mean(axis=0, keepdims=True)
    nperseg = min(64, max(16, len(sig) // 3))
    f, _, zxx = stft(sig.mean(axis=1), fs=fs_hz, nperseg=nperseg, noverlap=nperseg // 2)
    return f, np.abs(zxx).mean(axis=1)


def cluster_xy(points: list[tuple[float, float]], eps: float = 2.0) -> list[tuple[float, float]]:
    """Merge nearby detections into cluster centroids."""
    if not points:
        return []
    pts = np.array(points)
    used = np.zeros(len(pts), dtype=bool)
    clusters = []
    for i in range(len(pts)):
        if used[i]:
            continue
        dist = np.linalg.norm(pts - pts[i], axis=1)
        group = pts[dist < eps]
        used[dist < eps] = True
        clusters.append((float(group[:, 0].mean()), float(group[:, 1].mean())))
    return clusters


def detect_and_localize(
    csi: np.ndarray,
    fs_hz: float,
    area_size_m: float = 10.0,
    max_targets: int = 3,
    sensor_xy: tuple[float, float] = (5.0, 0.0),
) -> list[dict]:
    """
    Detect up to max_targets people and return XY positions.

    Uses delay-domain peaks (range) + subcarrier phase (angle) + Doppler (motion).
    Sensor reference: center of bottom edge (between nodes 1 and 2).
    """
    cleaned = srcc(csi)
    T, N = cleaned.shape
    if T < 8 or N < 4:
        return []

    delay_prof = _delay_profile(cleaned)
    d_max = delay_prof.max()
    if d_max <= 0:
        return []

    peaks, props = find_peaks(
        delay_prof,
        height=0.25 * d_max,
        distance=max(2, N // 20),
        prominence=0.08 * d_max,
    )
    if len(peaks) == 0:
        peaks = np.array([int(np.argmax(delay_prof))])

    if len(peaks) == 0:
        peaks = np.array([int(np.argmax(delay_prof))])
        props = {"peak_heights": np.array([float(d_max)])}

    scored = sorted(
        zip(peaks.tolist(), props["peak_heights"].tolist()),
        key=lambda x: -x[1],
    )
    scored = scored[: max_targets * 2]

    h = np.abs(np.fft.ifft(cleaned, axis=1))
    sx, sy = sensor_xy
    raw_points = []

    for delay_bin, height in scored:
        weights = h[:, delay_bin]
        angle = _subcarrier_angle(cleaned, weights)

        # Range from delay bin — scale to room diagonal
        r = (delay_bin / max(N - 1, 1)) * area_size_m * 1.1 + 0.8
        r = min(r, area_size_m * 1.35)

        x = sx + r * np.sin(angle)
        y = sy + r * np.cos(angle)
        x = float(np.clip(x, 0.5, area_size_m - 0.5))
        y = float(np.clip(y, 0.5, area_size_m - 0.5))

        # Doppler velocity for this target
        seg = cleaned[:, max(0, delay_bin - 2) : min(N, delay_bin + 3)]
        sig = np.abs(seg).mean(axis=1) - np.abs(seg).mean()
        vel = 0.0
        if len(sig) > 16:
            f, _, zxx = stft(sig, fs=fs_hz, nperseg=min(32, len(sig) // 2), noverlap=8)
            power = np.abs(zxx) ** 2
            if power.size:
                fi = np.unravel_index(np.argmax(power), power.shape)[0]
                doppler_hz = float(f[fi]) if fi < len(f) else 0.0
                vel = abs(doppler_hz * 299792458.0 / (2 * 2.4e9))

        raw_points.append({
            "x_m": x,
            "y_m": y,
            "velocity_mps": float(vel),
            "weight": float(height),
            "delay_bin": int(delay_bin),
        })

    # Cluster to remove duplicate peaks → true people count
    centroids = cluster_xy([(p["x_m"], p["y_m"]) for p in raw_points], eps=2.0)
    centroids = centroids[:max_targets]

    detections = []
    for cx, cy in centroids:
        best = min(raw_points, key=lambda p: (p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2)
        detections.append({
            "x_m": cx,
            "y_m": cy,
            "velocity_mps": best["velocity_mps"],
            "weight": best["weight"],
            "delay_bin": best["delay_bin"],
            "dt": 1.0 / fs_hz,
        })

    return detections
