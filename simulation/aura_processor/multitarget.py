"""Multi-target detection, clustering, and XY localization from CSI."""

from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks, stft, detrend

from .srcc import srcc


def trim_csi_to_video(
    csi: np.ndarray,
    timestamps_ms: np.ndarray,
    video_duration_sec: float,
) -> tuple[np.ndarray, np.ndarray, float]:
    """
    Align CSI with video duration.

    If packet count implies high-rate capture during the video (e.g. 2869 pkt / 3s),
    use ALL packets even when timestamps wrongly span minutes.
    """
    n = len(csi)
    if n == 0:
        return csi, timestamps_ms, 20.0

    duration = max(video_duration_sec, 0.1)
    implied_fs = (n - 1) / duration

    if len(timestamps_ms) > 1:
        t0 = float(timestamps_ms[0])
        span_sec = (float(timestamps_ms[-1]) - t0) / 1000.0
        ts_fs = (n - 1) / span_sec if span_sec > 0.01 else implied_fs

        # High packet count for video length OR timestamps clearly wrong → keep all frames
        if implied_fs > 80 or (span_sec > duration * 1.5 and implied_fs > 25):
            ts = np.linspace(0, duration * 1000.0, n)
            fs = float(np.clip(implied_fs, 10.0, 2000.0))
            return csi, ts, fs

        if span_sec > duration * 1.2:
            mask = (timestamps_ms - t0) <= duration * 1000.0 + 1.0
            csi = csi[mask]
            timestamps_ms = timestamps_ms[mask] - t0
        else:
            timestamps_ms = timestamps_ms - t0
        fs = (len(csi) - 1) / duration if len(csi) > 1 else implied_fs
    else:
        ts = np.linspace(0, duration * 1000.0, n)
        timestamps_ms = ts
        fs = implied_fs

    fs = float(np.clip(fs, 10.0, 2000.0))
    return csi, timestamps_ms, fs


def _delay_profile(csi: np.ndarray) -> np.ndarray:
    h = np.abs(np.fft.ifft(csi, axis=1))
    return h.mean(axis=0)


def _subcarrier_angle(csi: np.ndarray, weights: np.ndarray | None = None) -> float:
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


def cluster_xy(
    points: list[tuple[float, float]],
    eps: float = 2.0,
    max_clusters: int = 6,
) -> list[tuple[float, float]]:
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
    return clusters[:max_clusters]


def _localize_from_delay_bin(
    cleaned: np.ndarray,
    delay_bin: int,
    height: float,
    fs_hz: float,
    area_size_m: float,
    sensor_xy: tuple[float, float],
) -> dict:
    h = np.abs(np.fft.ifft(cleaned, axis=1))
    N = cleaned.shape[1]
    weights = h[:, delay_bin]
    angle = _subcarrier_angle(cleaned, weights)
    sx, sy = sensor_xy
    r = (delay_bin / max(N - 1, 1)) * area_size_m * 1.15 + 0.6
    r = min(r, area_size_m * 1.4)
    x = float(np.clip(sx + r * np.sin(angle), 0.5, area_size_m - 0.5))
    y = float(np.clip(sy + r * np.cos(angle), 0.5, area_size_m - 0.5))

    seg = cleaned[:, max(0, delay_bin - 2) : min(N, delay_bin + 3)]
    sig = detrend(np.abs(seg).mean(axis=1), type="linear")
    vel = 0.0
    if len(sig) > 32:
        nperseg = min(128, max(32, len(sig) // 4))
        f, _, zxx = stft(sig, fs=fs_hz, nperseg=nperseg, noverlap=nperseg // 2)
        power = np.abs(zxx) ** 2
        if power.size:
            fi = int(np.unravel_index(np.argmax(power), power.shape)[0])
            vel = abs(float(f[fi]) * 299792458.0 / (2 * 2.4e9))

    return {
        "x_m": x, "y_m": y,
        "velocity_mps": vel,
        "weight": height,
        "delay_bin": int(delay_bin),
        "dt": 1.0 / fs_hz,
    }


def _iterative_delay_peaks(
    cleaned: np.ndarray,
    fs_hz: float,
    area_size_m: float,
    max_targets: int,
    sensor_xy: tuple[float, float],
) -> list[dict]:
    """Find multiple people via iterative strongest-delay cancellation."""
    delay_prof = _delay_profile(cleaned)
    residual = delay_prof.copy()
    N = len(delay_prof)
    dets = []

    for _ in range(max_targets):
        if residual.max() <= 0:
            break
        peak = int(np.argmax(residual))
        height = float(delay_prof[peak])
        if height < 0.12 * delay_prof.max():
            break
        dets.append(_localize_from_delay_bin(cleaned, peak, height, fs_hz, area_size_m, sensor_xy))
        lo = max(0, peak - max(2, N // 15))
        hi = min(N, peak + max(2, N // 15) + 1)
        residual[lo:hi] = 0

    return dets


def _svd_motion_sources(csi: np.ndarray, n_sources: int = 3) -> list[np.ndarray]:
    """Separate independent motion sources via SVD on detrended phase."""
    phase = np.angle(csi)
    phase = detrend(phase, axis=0, type="linear")
    phase = phase - phase.mean(axis=0, keepdims=True)
    try:
        U, S, Vh = np.linalg.svd(phase, full_matrices=False)
    except np.linalg.LinAlgError:
        return []

    sources = []
    for i in range(min(n_sources, len(S))):
        if S[i] < 0.05 * S[0]:
            continue
        comp = (U[:, i : i + 1] * S[i]) @ Vh[i : i + 1, :]
        sources.append(comp)
    return sources


def _localize_from_source(
    source_phase: np.ndarray,
    fs_hz: float,
    area_size_m: float,
    sensor_xy: tuple[float, float],
    sc_offset: int = 0,
) -> dict | None:
    """Localize one SVD motion component."""
    pseudo = np.exp(1j * source_phase)
    delay_prof = _delay_profile(pseudo)
    if delay_prof.max() <= 0:
        return None
    peak = int(np.argmax(delay_prof))
    det = _localize_from_delay_bin(pseudo, peak, float(delay_prof[peak]), fs_hz, area_size_m, sensor_xy)
    # Spread sources across angle using component index
    angle_shift = (sc_offset - 1) * 0.45
    sx, sy = sensor_xy
    r = np.hypot(det["x_m"] - sx, det["y_m"] - sy)
    base_angle = np.arctan2(det["x_m"] - sx, det["y_m"] - sy + 1e-6)
    ang = base_angle + angle_shift
    det["x_m"] = float(np.clip(sx + r * np.sin(ang), 0.5, area_size_m - 0.5))
    det["y_m"] = float(np.clip(sy + r * np.cos(ang), 0.5, area_size_m - 0.5))
    return det


def detect_and_localize(
    csi: np.ndarray,
    fs_hz: float,
    area_size_m: float = 10.0,
    max_targets: int = 3,
    sensor_xy: tuple[float, float] = (5.0, 0.0),
) -> list[dict]:
    """Detect up to max_targets people using SVD separation + iterative delay peaks."""
    cleaned = srcc(csi)
    T, N = cleaned.shape
    if T < 8 or N < 4:
        return []

    raw_points: list[dict] = []

    # Method 1: SVD motion sources (finds weak + strong movers)
    sources = _svd_motion_sources(cleaned, n_sources=max_targets)
    for i, src in enumerate(sources):
        det = _localize_from_source(src, fs_hz, area_size_m, sensor_xy, sc_offset=i)
        if det:
            raw_points.append(det)

    # Method 2: Iterative delay peaks on full signal
    raw_points.extend(_iterative_delay_peaks(cleaned, fs_hz, area_size_m, max_targets, sensor_xy))

    # Method 3: Subcarrier band splitting (left/center/right of spectrum)
    thirds = np.array_split(np.arange(N), 3)
    for i, band in enumerate(thirds):
        if len(band) < 2:
            continue
        sub = cleaned[:, band]
        delay_prof = _delay_profile(sub)
        peak = int(np.argmax(delay_prof))
        global_peak = int(band[peak]) if peak < len(band) else int(band[len(band) // 2])
        det = _localize_from_delay_bin(sub, peak, float(delay_prof[peak]), fs_hz, area_size_m, sensor_xy)
        det["delay_bin"] = global_peak
        raw_points.append(det)

    if not raw_points:
        return []

    centroids = cluster_xy([(p["x_m"], p["y_m"]) for p in raw_points], eps=2.2, max_clusters=max_targets)

    detections = []
    for cx, cy in centroids:
        best = min(raw_points, key=lambda p: (p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2)
        detections.append({**best, "x_m": cx, "y_m": cy})

    return detections[:max_targets]


def detect_session_targets(
    csi: np.ndarray,
    fs_hz: float,
    area_size_m: float = 10.0,
    max_targets: int = 3,
    sensor_xy: tuple[float, float] = (5.0, 0.0),
    window_sec: float = 0.5,
) -> list[dict]:
    """
    Aggregate detections across entire CSI session → stable multi-person positions.
    Finds jumping (strong) AND stationary (weak) people.
    """
    cleaned = srcc(csi)
    T = len(cleaned)
    win = max(int(window_sec * fs_hz), 32)
    hop = max(win // 3, 8)

    all_points: list[dict] = []

    # Full-session SVD (best for separating 3 people)
    all_points.extend(detect_and_localize(cleaned, fs_hz, area_size_m, max_targets, sensor_xy))

    # Sliding windows
    for start in range(0, max(T - win + 1, 1), hop):
        chunk = cleaned[start : start + win]
        all_points.extend(detect_and_localize(chunk, fs_hz, area_size_m, max_targets, sensor_xy))

    if not all_points:
        return []

    centroids = cluster_xy([(p["x_m"], p["y_m"]) for p in all_points], eps=2.5, max_clusters=max_targets)

    session_dets = []
    for cx, cy in centroids:
        nearby = [p for p in all_points if (p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2 < 6.25]
        vel = float(np.median([p["velocity_mps"] for p in nearby])) if nearby else 0.0
        best = min(nearby, key=lambda p: -p.get("weight", 0)) if nearby else all_points[0]
        session_dets.append({
            "x_m": cx,
            "y_m": cy,
            "velocity_mps": vel,
            "weight": best.get("weight", 1.0),
            "delay_bin": best.get("delay_bin", 0),
            "dt": 1.0 / fs_hz,
        })

    return session_dets[:max_targets]
