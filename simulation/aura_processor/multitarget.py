"""Multi-target detection, clustering, and XY localization from CSI only."""

from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks, stft, detrend

from .srcc import srcc, motion_energy

# Tunable CSI detection gates (reduce false positives)
PEAK_HEIGHT_RATIO = 0.15
SVD_SINGULAR_RATIO = 0.10
MIN_DETECTION_SCORE = 0.12
SESSION_VOTE_MIN_WINDOWS = 2
CLUSTER_EPS_M = 2.0


def trim_csi_to_video(
    csi: np.ndarray,
    timestamps_ms: np.ndarray,
    video_duration_sec: float,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Align CSI with video duration."""
    n = len(csi)
    if n == 0:
        return csi, timestamps_ms, 20.0

    duration = max(video_duration_sec, 0.1)
    implied_fs = (n - 1) / duration

    if len(timestamps_ms) > 1:
        t0 = float(timestamps_ms[0])
        span_sec = (float(timestamps_ms[-1]) - t0) / 1000.0

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
        timestamps_ms = np.linspace(0, duration * 1000.0, n)
        fs = implied_fs

    return csi, timestamps_ms, float(np.clip(fs, 10.0, 2000.0))


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
    eps: float = CLUSTER_EPS_M,
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


def _score_detection(cleaned: np.ndarray, det: dict) -> float:
    """Higher = more likely a real person (not noise)."""
    prof_max = float(_delay_profile(cleaned).max()) + 1e-9
    peak_ratio = float(det.get("weight", 0)) / prof_max

    db = int(det.get("delay_bin", 0))
    n_sc = cleaned.shape[1]
    lo, hi = max(0, db - 3), min(n_sc, db + 4)
    seg = cleaned[:, lo:hi]
    if seg.size == 0:
        return peak_ratio * 0.5

    amp_var = float(np.var(np.abs(seg)))
    phase_var = float(np.var(np.diff(np.angle(seg), axis=0)))
    motion_band = float(np.mean(np.var(np.abs(seg), axis=1)))

    score = peak_ratio * 0.45 + amp_var * 0.25 + phase_var * 0.15 + motion_band * 0.15
    return float(score)


def filter_confident_detections(
    detections: list[dict],
    cleaned: np.ndarray,
    min_score: float = MIN_DETECTION_SCORE,
    max_targets: int = 3,
) -> list[dict]:
    if not detections:
        return []
    scored = [( _score_detection(cleaned, d), d) for d in detections]
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, det in scored:
        if score < min_score:
            continue
        det = dict(det)
        det["confidence"] = score
        out.append(det)
        if len(out) >= max_targets:
            break
    return out


def _localize_from_delay_bin(
    cleaned: np.ndarray,
    delay_bin: int,
    height: float,
    fs_hz: float,
    area_size_m: float,
    sensor_xy: tuple[float, float],
) -> dict:
    h = np.abs(np.fft.ifft(cleaned, axis=1))
    n_sc = cleaned.shape[1]
    weights = h[:, delay_bin]
    angle = _subcarrier_angle(cleaned, weights)
    sx, sy = sensor_xy
    r = (delay_bin / max(n_sc - 1, 1)) * area_size_m * 1.15 + 0.6
    r = min(r, area_size_m * 1.4)
    x = float(np.clip(sx + r * np.sin(angle), 0.5, area_size_m - 0.5))
    y = float(np.clip(sy + r * np.cos(angle), 0.5, area_size_m - 0.5))

    seg = cleaned[:, max(0, delay_bin - 2) : min(n_sc, delay_bin + 3)]
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
        "x_m": x,
        "y_m": y,
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
    delay_prof = _delay_profile(cleaned)
    residual = delay_prof.copy()
    n_bins = len(delay_prof)
    dets = []

    for _ in range(max_targets):
        if residual.max() <= 0:
            break
        peak = int(np.argmax(residual))
        height = float(delay_prof[peak])
        if height < PEAK_HEIGHT_RATIO * delay_prof.max():
            break
        dets.append(_localize_from_delay_bin(cleaned, peak, height, fs_hz, area_size_m, sensor_xy))
        lo = max(0, peak - max(2, n_bins // 12))
        hi = min(n_bins, peak + max(2, n_bins // 12) + 1)
        residual[lo:hi] = 0

    return dets


def _svd_motion_sources(csi: np.ndarray, n_sources: int = 3) -> list[np.ndarray]:
    phase = np.angle(csi)
    phase = detrend(phase, axis=0, type="linear")
    phase = phase - phase.mean(axis=0, keepdims=True)
    try:
        u, s, vh = np.linalg.svd(phase, full_matrices=False)
    except np.linalg.LinAlgError:
        return []

    sources = []
    for i in range(min(n_sources, len(s))):
        if s[i] < SVD_SINGULAR_RATIO * s[0]:
            continue
        comp = (u[:, i : i + 1] * s[i]) @ vh[i : i + 1, :]
        sources.append(comp)
    return sources


def _localize_from_source(
    source_phase: np.ndarray,
    fs_hz: float,
    area_size_m: float,
    sensor_xy: tuple[float, float],
) -> dict | None:
    pseudo = np.exp(1j * source_phase)
    delay_prof = _delay_profile(pseudo)
    if delay_prof.max() <= 0:
        return None
    peak = int(np.argmax(delay_prof))
    return _localize_from_delay_bin(
        pseudo, peak, float(delay_prof[peak]), fs_hz, area_size_m, sensor_xy
    )


def detect_and_localize(
    csi: np.ndarray,
    fs_hz: float,
    area_size_m: float = 10.0,
    max_targets: int = 3,
    sensor_xy: tuple[float, float] = (5.0, 0.0),
    skip_srcc: bool = False,
    require_motion: bool = True,
    motion_level: float = 0.0,
    motion_threshold: float = 0.02,
) -> list[dict]:
    """CSI-only detection: SVD sources + delay peaks, confidence-filtered."""
    cleaned = csi if skip_srcc else srcc(csi)
    cleaned = np.nan_to_num(cleaned)
    t_len, n_sc = cleaned.shape
    if t_len < 16 or n_sc < 4:
        return []

    if require_motion and motion_level < motion_threshold * 0.8:
        return []

    raw_points: list[dict] = []

    for src in _svd_motion_sources(cleaned, n_sources=max_targets):
        det = _localize_from_source(src, fs_hz, area_size_m, sensor_xy)
        if det:
            raw_points.append(det)

    raw_points.extend(_iterative_delay_peaks(cleaned, fs_hz, area_size_m, max_targets, sensor_xy))

    if not raw_points:
        return []

    centroids = cluster_xy([(p["x_m"], p["y_m"]) for p in raw_points], eps=CLUSTER_EPS_M, max_clusters=max_targets)
    merged: list[dict] = []
    for cx, cy in centroids:
        best = min(raw_points, key=lambda p: (p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2)
        merged.append({**best, "x_m": cx, "y_m": cy})

    return filter_confident_detections(merged, cleaned, max_targets=max_targets)


def detect_session_targets(
    csi: np.ndarray,
    fs_hz: float,
    area_size_m: float = 10.0,
    max_targets: int = 3,
    sensor_xy: tuple[float, float] = (5.0, 0.0),
    window_sec: float = 0.5,
    motion_threshold: float = 0.02,
) -> list[dict]:
    """
    Aggregate confident CSI detections across sliding windows (temporal voting).
    Returns only targets confirmed in multiple windows or with high confidence.
    """
    t_len = len(csi)
    if t_len < 32:
        return []

    cleaned = np.nan_to_num(srcc(csi))
    motion_level = float(np.mean(motion_energy(cleaned)))
    if motion_level < motion_threshold * 0.75:
        return []

    win = max(int(window_sec * fs_hz), 48)
    hop = max(win // 4, 16)

    window_hits: list[list[dict]] = []
    for start in range(0, max(t_len - win + 1, 1), hop):
        chunk = cleaned[start : start + win]
        m_chunk = float(np.mean(motion_energy(chunk)))
        dets = detect_and_localize(
            chunk,
            fs_hz,
            area_size_m,
            max_targets,
            sensor_xy,
            skip_srcc=True,
            require_motion=True,
            motion_level=m_chunk,
            motion_threshold=motion_threshold,
        )
        if dets:
            window_hits.append(dets)

    # Full-session pass
    full_dets = detect_and_localize(
        cleaned,
        fs_hz,
        area_size_m,
        max_targets,
        sensor_xy,
        skip_srcc=True,
        require_motion=True,
        motion_level=motion_level,
        motion_threshold=motion_threshold,
    )
    if full_dets:
        window_hits.append(full_dets)

    if not window_hits:
        return []

    # Vote: cluster all confident points, keep clusters seen in >= SESSION_VOTE_MIN_WINDOWS
    all_points: list[dict] = [d for group in window_hits for d in group]
    centroids = cluster_xy([(p["x_m"], p["y_m"]) for p in all_points], eps=CLUSTER_EPS_M, max_clusters=max_targets)

    session_dets: list[dict] = []
    for cx, cy in centroids:
        nearby = [p for p in all_points if (p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2 < 4.0]
        windows_with_hit = sum(
            1 for group in window_hits
            if any((p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2 < 4.0 for p in group)
        )
        best = max(nearby, key=lambda p: p.get("confidence", p.get("weight", 0)))
        conf = float(best.get("confidence", _score_detection(cleaned, best)))
        if windows_with_hit < SESSION_VOTE_MIN_WINDOWS and conf < 0.28:
            continue
        vel = float(np.median([p["velocity_mps"] for p in nearby])) if nearby else 0.0
        session_dets.append({
            "x_m": cx,
            "y_m": cy,
            "velocity_mps": vel,
            "weight": best.get("weight", 1.0),
            "confidence": conf,
            "delay_bin": best.get("delay_bin", 0),
            "dt": 1.0 / fs_hz,
        })

    session_dets.sort(key=lambda d: -d.get("confidence", 0))
    return session_dets[:max_targets]
