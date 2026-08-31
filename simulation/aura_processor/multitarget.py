"""Multi-target detection, clustering, and XY localization from CSI only."""

from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks, stft, detrend

from .srcc import srcc, motion_energy

CLUSTER_EPS_M = 1.75
MAX_PEOPLE_DEFAULT = 6


def preprocess_csi(csi: np.ndarray) -> np.ndarray:
    """Dataset-agnostic normalization — gentle scaling to avoid amplifying noise."""
    out = np.nan_to_num(np.asarray(csi, dtype=np.complex64))
    if out.ndim != 2 or out.size == 0:
        return out
    out = out - np.mean(out, axis=0, keepdims=True)
    scale = np.median(np.abs(out), axis=0) + 1e-6
    out = out / scale
    return out


def estimate_person_count(
    cleaned: np.ndarray,
    motion_level: float,
    motion_threshold: float = 0.02,
    max_people: int = MAX_PEOPLE_DEFAULT,
) -> int:
    """
    Estimate how many people are present from CSI motion + delay/SVD structure.
    Returns 0 when the scene is static (no false counts).
    """
    if motion_level < motion_threshold * 0.70:
        return 0

    gates = _adaptive_gates(motion_level, motion_threshold)
    t_len, n_sc = cleaned.shape
    if t_len < 16 or n_sc < 4:
        return 0

    estimates: list[int] = []

    # SVD motion sources — require clear singular-value drop-off
    try:
        phase = detrend(np.angle(cleaned), axis=0, type="linear")
        phase -= phase.mean(axis=0, keepdims=True)
        _, s, _ = np.linalg.svd(phase, full_matrices=False)
        if len(s) >= 2 and s[0] > 0:
            n_svd = 0
            for i, sv in enumerate(s[:max_people]):
                if sv < gates["svd_ratio"] * s[0]:
                    break
                if i > 0 and sv > 0.82 * s[i - 1]:
                    break
                n_svd = i + 1
            if n_svd > 0:
                estimates.append(n_svd)
    except np.linalg.LinAlgError:
        pass

    # Distinct delay peaks with prominence (rejects noise floor)
    prof = _delay_profile(cleaned)
    if prof.max() > 0:
        prom = gates["peak_ratio"] * prof.max() * 0.45
        peaks, _ = find_peaks(
            prof,
            height=gates["peak_ratio"] * prof.max(),
            distance=max(2, len(prof) // 12),
            prominence=max(prom, 1e-9),
        )
        if len(peaks):
            estimates.append(len(peaks))

    # Active subcarrier bands — only if variance is uneven (structured motion)
    n_bands = min(max_people, max(2, n_sc // 6))
    bands = np.array_split(np.arange(n_sc), n_bands)
    amp = np.abs(cleaned)
    band_vars = [float(np.mean(np.var(amp[:, b], axis=1))) for b in bands if len(b) > 1]
    if band_vars:
        med = float(np.median(band_vars))
        spread = float(np.std(band_vars)) / (med + 1e-9)
        if spread > 0.12:
            thresh = med * 1.35
            estimates.append(int(np.sum(np.array(band_vars) > thresh)))

    if not estimates:
        return 0

    count = int(np.round(np.median(estimates)))
    ratio = motion_level / max(motion_threshold, 1e-6)
    peak_est = max(estimates)
    if ratio >= 3.0 and peak_est > count:
        if sum(1 for e in estimates if e >= peak_est) >= 2:
            count = peak_est
    if len(estimates) == 1 and count > 2:
        count = min(count, 2)
    return int(np.clip(count, 1, max_people))


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


def _adaptive_gates(motion_level: float, motion_threshold: float) -> dict:
    """Relax CSI peak gates when motion is clearly present."""
    ratio = motion_level / max(motion_threshold, 1e-6)
    if ratio >= 4.0:
        return {"peak_ratio": 0.07, "min_score": 0.035, "svd_ratio": 0.05, "vote_windows": 1}
    if ratio >= 2.0:
        return {"peak_ratio": 0.09, "min_score": 0.055, "svd_ratio": 0.07, "vote_windows": 1}
    if ratio >= 1.0:
        return {"peak_ratio": 0.11, "min_score": 0.08, "svd_ratio": 0.08, "vote_windows": 2}
    return {"peak_ratio": 0.15, "min_score": 0.12, "svd_ratio": 0.10, "vote_windows": 2}


def _delay_profile(csi: np.ndarray) -> np.ndarray:
    h = np.abs(np.fft.ifft(csi, axis=1))
    return h.mean(axis=0)


def _subcarrier_angle(csi: np.ndarray, weights: np.ndarray | None = None, delay_bin: int | None = None) -> float:
    """AoA from phase slope across subcarriers near the delay peak."""
    n_sc = csi.shape[1]
    if delay_bin is not None and n_sc > 8:
        lo = max(0, delay_bin - 8)
        hi = min(n_sc, delay_bin + 9)
        seg = csi[:, lo:hi]
        if weights is None:
            weights = np.mean(np.abs(seg), axis=0)
        phase = np.angle(seg)
        sc_offset = lo
    else:
        seg = csi
        phase = np.angle(csi)
        sc_offset = 0
        if weights is not None and len(weights) != len(csi):
            weights = None

    if weights is not None and len(weights) == seg.shape[1]:
        w = weights / (weights.sum() + 1e-8)
        mean_phase = np.average(phase, axis=0, weights=w)
    else:
        mean_phase = phase.mean(axis=0)

    mean_phase = np.unwrap(mean_phase)
    sc = np.arange(len(mean_phase)) + sc_offset
    slope = np.polyfit(sc, mean_phase, 1)[0]
    return float(np.clip(slope * 2.2, -1.2, 1.2))


def _range_from_delay_bin(delay_bin: int, n_sc: int, prof: np.ndarray, area_size_m: float) -> float:
    """Map delay bin to range using direct-path reference (more stable across datasets)."""
    n = max(n_sc - 1, 1)
    early = prof[: max(n // 3, 2)]
    direct_bin = int(np.argmax(early)) if early.size else 0
    rel = max(0, delay_bin - direct_bin)
    r = 0.7 + (rel / n) * area_size_m * 1.05
    return float(np.clip(r, 0.5, area_size_m * 1.35))


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
    prof = _delay_profile(cleaned)
    prof_max = float(prof.max()) + 1e-9
    peak_ratio = float(det.get("weight", 0)) / prof_max

    db = int(det.get("delay_bin", 0))
    n_sc = cleaned.shape[1]
    lo, hi = max(0, db - 3), min(n_sc, db + 4)
    seg = cleaned[:, lo:hi]
    if seg.size == 0:
        return peak_ratio

    amp_var = float(np.var(np.abs(seg)))
    phase_var = float(np.var(np.diff(np.angle(seg), axis=0)))
    t_var = float(np.mean(np.var(np.abs(seg), axis=1)))
    baseline = float(np.var(np.abs(cleaned))) + 1e-9

    score = (
        peak_ratio * 0.40
        + min(amp_var / baseline, 3.0) * 0.20
        + min(phase_var, 1.0) * 0.20
        + min(t_var / baseline, 3.0) * 0.20
    )
    return float(score)


def filter_confident_detections(
    detections: list[dict],
    cleaned: np.ndarray,
    min_score: float,
    max_targets: int = 3,
) -> list[dict]:
    if not detections:
        return []
    scored = [(_score_detection(cleaned, d), d) for d in detections]
    scored.sort(key=lambda x: -x[0])
    out = []
    for score, det in scored:
        if score < min_score:
            continue
        d = dict(det)
        d["confidence"] = score
        out.append(d)
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
    prof = _delay_profile(cleaned)
    weights = h[:, delay_bin]
    angle = _subcarrier_angle(cleaned, weights, delay_bin=delay_bin)
    sx, sy = sensor_xy
    r = _range_from_delay_bin(delay_bin, n_sc, prof, area_size_m)
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
    peak_ratio: float,
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
        if height < peak_ratio * delay_prof.max():
            break
        dets.append(_localize_from_delay_bin(cleaned, peak, height, fs_hz, area_size_m, sensor_xy))
        lo = max(0, peak - max(2, n_bins // 12))
        hi = min(n_bins, peak + max(2, n_bins // 12) + 1)
        residual[lo:hi] = 0

    return dets


def _delay_peak_candidates(
    cleaned: np.ndarray,
    fs_hz: float,
    area_size_m: float,
    max_targets: int,
    sensor_xy: tuple[float, float],
    peak_ratio: float,
) -> list[dict]:
    """Find multiple delay peaks via scipy find_peaks (robust on real CSI)."""
    prof = _delay_profile(cleaned)
    if prof.max() <= 0:
        return []
    peaks, _ = find_peaks(
        prof,
        height=peak_ratio * prof.max(),
        distance=max(2, len(prof) // 14),
    )
    if len(peaks) == 0:
        peaks = np.argsort(prof)[-max_targets:]
    dets = []
    for peak in peaks[:max_targets]:
        dets.append(_localize_from_delay_bin(cleaned, int(peak), float(prof[peak]), fs_hz, area_size_m, sensor_xy))
    return dets


def _band_motion_sources(
    cleaned: np.ndarray,
    fs_hz: float,
    area_size_m: float,
    max_targets: int,
    sensor_xy: tuple[float, float],
) -> list[dict]:
    """Separate people via subcarrier bands ranked by temporal motion energy."""
    n_sc = cleaned.shape[1]
    if n_sc < 6 or max_targets <= 0:
        return []
    n_bands = min(max_targets, max(2, n_sc // 6))
    bands = np.array_split(np.arange(n_sc), n_bands)
    amp = np.abs(cleaned)
    band_vars: list[tuple[float, np.ndarray, np.ndarray]] = []
    for band in bands:
        if len(band) < 2:
            continue
        sub = cleaned[:, band]
        var_t = float(np.mean(np.var(amp[:, band], axis=1)))
        band_vars.append((var_t, sub, band))
    band_vars.sort(key=lambda x: -x[0])
    med = float(np.median([v for v, _, _ in band_vars])) if band_vars else 0.0
    dets = []
    for var_t, sub, band in band_vars:
        if var_t < med * 0.85:
            continue
        prof = _delay_profile(sub)
        peak = int(np.argmax(prof))
        global_bin = int(band[min(peak, len(band) - 1)])
        det = _localize_from_delay_bin(sub, peak, float(prof[peak]), fs_hz, area_size_m, sensor_xy)
        det["delay_bin"] = global_bin
        det["weight"] = float(prof[peak] * (1.0 + var_t))
        dets.append(det)
        if len(dets) >= max_targets:
            break
    return dets


def _svd_motion_sources(csi: np.ndarray, n_sources: int, svd_ratio: float) -> list[np.ndarray]:
    phase = np.angle(csi)
    phase = detrend(phase, axis=0, type="linear")
    phase = phase - phase.mean(axis=0, keepdims=True)
    try:
        u, s, vh = np.linalg.svd(phase, full_matrices=False)
    except np.linalg.LinAlgError:
        return []

    sources = []
    for i in range(min(n_sources, len(s))):
        if s[i] < svd_ratio * s[0]:
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
    """CSI-only detection with motion-adaptive thresholds."""
    if skip_srcc:
        cleaned = np.nan_to_num(csi)
    else:
        cleaned = np.nan_to_num(srcc(preprocess_csi(csi)))
    t_len, n_sc = cleaned.shape
    if t_len < 16 or n_sc < 4:
        return []

    if require_motion and motion_level < motion_threshold * 0.7:
        return []

    gates = _adaptive_gates(motion_level, motion_threshold)
    raw_points: list[dict] = []

    for src in _svd_motion_sources(cleaned, max_targets, gates["svd_ratio"]):
        det = _localize_from_source(src, fs_hz, area_size_m, sensor_xy)
        if det:
            raw_points.append(det)

    raw_points.extend(_iterative_delay_peaks(
        cleaned, fs_hz, area_size_m, max_targets, sensor_xy, gates["peak_ratio"]
    ))
    raw_points.extend(_delay_peak_candidates(
        cleaned, fs_hz, area_size_m, max_targets, sensor_xy, gates["peak_ratio"] * 0.85
    ))

    if motion_level >= motion_threshold:
        raw_points.extend(_band_motion_sources(cleaned, fs_hz, area_size_m, max_targets, sensor_xy))

    if not raw_points:
        return []

    centroids = cluster_xy([(p["x_m"], p["y_m"]) for p in raw_points], eps=CLUSTER_EPS_M, max_clusters=max_targets)
    merged: list[dict] = []
    for cx, cy in centroids:
        nearby = [p for p in raw_points if (p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2 < 3.5]
        if nearby:
            ws = np.array([p.get("weight", 1.0) for p in nearby], dtype=float)
            ws /= ws.sum() + 1e-9
            cx = float(np.sum([p["x_m"] * w for p, w in zip(nearby, ws)]))
            cy = float(np.sum([p["y_m"] * w for p, w in zip(nearby, ws)]))
        best = min(raw_points, key=lambda p: (p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2)
        merged.append({**best, "x_m": cx, "y_m": cy})

    return filter_confident_detections(merged, cleaned, gates["min_score"], max_targets)


def detect_session_targets(
    csi: np.ndarray,
    fs_hz: float,
    area_size_m: float = 10.0,
    max_targets: int = 3,
    sensor_xy: tuple[float, float] = (5.0, 0.0),
    window_sec: float = 0.5,
    motion_threshold: float = 0.02,
) -> list[dict]:
    """Aggregate CSI detections across sliding windows with temporal voting."""
    t_len = len(csi)
    if t_len < 32:
        return []

    raw = preprocess_csi(csi)
    cleaned = np.nan_to_num(srcc(raw))
    motion_level = float(np.mean(motion_energy(cleaned)))
    if motion_level < motion_threshold * 0.65:
        return []

    # Auto-estimate how many people are in this CSI session
    estimated = estimate_person_count(cleaned, motion_level, motion_threshold, max_people=max_targets)
    if estimated <= 0:
        return []
    active_max = min(max_targets, estimated)

    gates = _adaptive_gates(motion_level, motion_threshold)
    win = max(int(window_sec * fs_hz), 48)
    hop = max(win // 4, 16)

    window_hits: list[list[dict]] = []
    for start in range(0, max(t_len - win + 1, 1), hop):
        chunk = cleaned[start : start + win]
        m_chunk = float(np.mean(motion_energy(chunk)))
        dets = detect_and_localize(
            chunk, fs_hz, area_size_m, active_max, sensor_xy,
            skip_srcc=True, require_motion=True,
            motion_level=m_chunk, motion_threshold=motion_threshold,
        )
        if dets:
            window_hits.append(dets)

    full_dets = detect_and_localize(
        cleaned, fs_hz, area_size_m, active_max, sensor_xy,
        skip_srcc=True, require_motion=True,
        motion_level=motion_level, motion_threshold=motion_threshold,
    )
    if full_dets:
        window_hits.append(full_dets)

    if not window_hits and motion_level >= motion_threshold:
        fallback = filter_confident_detections(
            _band_motion_sources(cleaned, fs_hz, area_size_m, active_max, sensor_xy)
            + _delay_peak_candidates(cleaned, fs_hz, area_size_m, active_max, sensor_xy, gates["peak_ratio"] * 0.7),
            cleaned,
            gates["min_score"] * 0.8,
            active_max,
        )
        if fallback:
            return fallback

    if not window_hits:
        return []

    all_points: list[dict] = [d for group in window_hits for d in group]
    centroids = cluster_xy([(p["x_m"], p["y_m"]) for p in all_points], eps=CLUSTER_EPS_M, max_clusters=active_max)

    session_dets: list[dict] = []
    min_votes = gates["vote_windows"]
    conf_floor = gates["min_score"] * 1.5

    for cx, cy in centroids:
        nearby = [p for p in all_points if (p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2 < 3.5]
        windows_with_hit = sum(
            1 for group in window_hits
            if any((p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2 < 3.5 for p in group)
        )
        best = max(nearby, key=lambda p: p.get("confidence", p.get("weight", 0)))
        conf = float(best.get("confidence", _score_detection(cleaned, best)))
        if windows_with_hit < min_votes and conf < conf_floor:
            continue
        vel = float(np.median([p["velocity_mps"] for p in nearby])) if nearby else 0.0
        if nearby:
            ws = np.array([p.get("confidence", p.get("weight", 1.0)) for p in nearby], dtype=float)
            ws /= ws.sum() + 1e-9
            rx = float(np.sum([p["x_m"] * w for p, w in zip(nearby, ws)]))
            ry = float(np.sum([p["y_m"] * w for p, w in zip(nearby, ws)]))
        else:
            rx, ry = cx, cy
        session_dets.append({
            "x_m": rx,
            "y_m": ry,
            "velocity_mps": vel,
            "weight": best.get("weight", 1.0),
            "confidence": conf,
            "delay_bin": best.get("delay_bin", 0),
            "dt": 1.0 / fs_hz,
        })

    session_dets.sort(key=lambda d: -d.get("confidence", 0))
    return session_dets[:active_max]
