"""Multi-target detection, clustering, and XY localization from CSI only."""

from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks, stft, detrend

from .srcc import srcc, motion_energy

CLUSTER_EPS_M = 1.35
MAX_PEOPLE_DEFAULT = 8


def _normalize_amp_2d(arr: np.ndarray) -> np.ndarray:
    """Collapse amplitude CSI to (time, subcarriers)."""
    a = np.asarray(arr)
    if np.iscomplexobj(a):
        a = np.abs(a)
    a = np.asarray(a, dtype=np.float64)
    if a.ndim == 1:
        return a.reshape(1, -1)
    if a.ndim == 2:
        return a
    if a.shape[-1] <= 128:
        flat = a.reshape(a.shape[0], -1, a.shape[-1])
        return np.mean(flat, axis=1)
    return a.reshape(a.shape[0], -1)


def _narrow_sc_gates(gates: dict, n_sc: int) -> dict:
    """Stricter peak/SVD gates for Intel/WiMANS 30-subcarrier CSI."""
    if n_sc > 40:
        return gates
    return {
        **gates,
        "peak_ratio": gates["peak_ratio"] * 1.55,
        "svd_ratio": max(gates["svd_ratio"], 0.14),
        "min_score": gates["min_score"] * 1.2,
    }


def _motion_signal_quality(cleaned: np.ndarray, motion_threshold: float) -> float:
    """How structured the CSI motion is (filters SRCC noise on static scenes)."""
    prof = _motion_delay_profile(cleaned)
    if prof.max() <= 0:
        return 0.0
    peak_ratio = float(prof.max() / (np.median(prof) + 1e-9))
    mcurve = motion_energy(cleaned)
    if len(mcurve) < 8:
        return 0.0
    periodicity = float(np.std(mcurve) / (np.mean(mcurve) + 1e-9))
    m_level = float(np.mean(mcurve))
    if m_level < motion_threshold * 0.5:
        return 0.0
    return float(np.clip(min(peak_ratio / 10.0, 1.0) * min(periodicity / 1.5, 1.0), 0.0, 1.0))


def _aoa_per_delay_bin(csi: np.ndarray, peak_bin: int) -> float:
    """Estimate AoA from subcarriers most correlated with motion at this delay bin."""
    n_sc = csi.shape[1]
    if n_sc < 4:
        return 0.0
    h = np.fft.ifft(csi, axis=1)
    peak_bin = int(np.clip(peak_bin, 0, h.shape[1] - 1))
    ref = h[:, peak_bin].astype(np.complex128)
    ref = ref - ref.mean()
    ref_norm = float(np.linalg.norm(ref)) + 1e-9
    cors = np.zeros(n_sc, dtype=np.float64)
    for sc in range(n_sc):
        s = h[:, sc].astype(np.complex128) - h[:, sc].mean()
        s_norm = float(np.linalg.norm(s)) + 1e-9
        cors[sc] = float(np.abs(np.vdot(ref, s))) / (ref_norm * s_norm)
    thresh = max(float(np.percentile(cors, 72)), float(cors.max()) * 0.72)
    mask = cors >= thresh
    if int(mask.sum()) < 2:
        mask = cors >= float(cors.max()) * 0.85
    idx = np.arange(n_sc, dtype=np.float64)
    com = float(np.sum(idx[mask] * cors[mask]) / (cors[mask].sum() + 1e-9))
    angle = (com - (n_sc - 1) / 2.0) / max(n_sc / 2.0, 1.0) * 1.05
    return float(np.clip(angle, -1.1, 1.1))


def _motion_delay_profile(csi: np.ndarray) -> np.ndarray:
    """Per-delay-bin temporal motion energy — distinguishes moving people from static multipath."""
    h = np.abs(np.fft.ifft(csi, axis=1))
    if h.shape[0] > 8:
        h = detrend(h, axis=0, type="linear")
    return np.var(h, axis=0)


def _range_from_delay_peak(prof: np.ndarray, peak_f: float, area_size_m: float) -> float:
    """Map delay peak index to range using this recording's delay spread."""
    n = max(len(prof) - 1, 1)
    weights = prof / (float(prof.sum()) + 1e-9)
    idx = np.arange(len(prof), dtype=np.float64)
    com = float(np.sum(idx * weights))
    spread = float(np.sqrt(np.sum(weights * (idx - com) ** 2))) + 1e-6
    rel = abs(peak_f - com) / spread
    r = 1.1 + rel * (area_size_m * 0.52)
    return float(np.clip(r, 0.8, area_size_m * 0.92))


def _count_motion_delay_peaks(
    cleaned: np.ndarray,
    gates: dict,
    max_people: int,
) -> int:
    """Count people from motion-heavy delay bins (dataset-specific)."""
    prof = _motion_delay_profile(cleaned)
    if prof.max() <= 0:
        return 0
    n_sc = cleaned.shape[1]
    height = gates["peak_ratio"] * float(prof.max())
    min_sep = max(4, len(prof) // 7) if n_sc <= 40 else max(3, len(prof) // 14)
    prom = max(height * 0.28, float(np.std(prof)) * 0.45)
    peaks, props = find_peaks(
        prof,
        height=height * 0.5,
        distance=min_sep,
        prominence=max(prom, 1e-9),
    )
    if len(peaks) == 0:
        peaks, props = find_peaks(prof, height=height * 0.35, distance=min_sep)
    if len(peaks) == 0:
        return 0
    prominences = props.get("prominences", prof[peaks])
    order = np.argsort(prominences)[::-1]
    max_h = float(prof.max())
    selected: list[int] = []
    for idx in order:
        p = int(peaks[idx])
        if float(prof[p]) < max_h * gates["peak_ratio"] * 0.7:
            continue
        if float(prominences[idx]) / max_h < 0.04:
            continue
        if all(abs(p - s) >= min_sep for s in selected):
            selected.append(p)
        if len(selected) >= max_people:
            break
    return len(selected)


def estimate_count_from_amplitude(
    amp: np.ndarray,
    motion_threshold: float = 0.02,
    max_people: int = MAX_PEOPLE_DEFAULT,
) -> int:
    """
    Estimate occupant count from preprocessed amplitude CSI (.npy).
    Complements complex .mat phase-based counting for WiMANS-style datasets.
    """
    a = _normalize_amp_2d(amp)
    if a.ndim != 2 or a.shape[0] < 24 or a.shape[1] < 4:
        return 0

    n_sc = a.shape[1]
    detrended = detrend(a, axis=0, type="linear")
    detrended = detrended - detrended.mean(axis=0, keepdims=True)
    m_level = float(np.mean(np.var(detrended, axis=0)))
    if m_level < motion_threshold * 0.35:
        return 0

    gates = _narrow_sc_gates(_adaptive_gates(m_level, motion_threshold), n_sc)
    pseudo = detrended.astype(np.complex64)

    motion_n = _count_motion_delay_peaks(pseudo, gates, max_people)
    delay_n = _delay_peak_count(pseudo, gates, max_people)
    if delay_n == 0:
        delay_n = _delay_peak_count_relaxed(pseudo, gates, max_people)

    n_svd = 0
    try:
        _, s, _ = np.linalg.svd(detrended, full_matrices=False)
        cap = min(max_people, max(2, n_sc // 8)) if n_sc <= 40 else max_people
        n_svd = _count_svd_sources(s, gates["svd_ratio"], cap)
    except np.linalg.LinAlgError:
        pass

    parts = [x for x in (motion_n, delay_n, n_svd) if x > 0]
    if not parts:
        return 0
    if len(parts) == 1:
        return int(np.clip(parts[0], 1, max_people))
    lo, hi = min(parts), max(parts)
    count = lo if hi - lo >= 2 else int(np.round(np.median(parts)))
    return int(np.clip(count, 1, max_people))


def _weighted_mean_axis0(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Column-wise weighted mean (numpy 2.4+ compatible)."""
    w = np.asarray(weights, dtype=float)
    v = np.asarray(values, dtype=float)
    if v.ndim == 1:
        return np.average(v, weights=w)
    w = w / (w.sum() + 1e-9)
    return np.sum(v * w, axis=0)


def adaptive_cluster_eps(expected_people: int, area_size_m: float) -> float:
    """Tighter clustering when more people are expected (keeps targets separated)."""
    n = max(expected_people, 1)
    return float(np.clip(area_size_m / (n * 1.45 + 2.0), 0.85, 2.2))


def _min_pairwise_distance(dets: list[dict]) -> float:
    if len(dets) < 2:
        return 99.0
    pts = np.array([(d["x_m"], d["y_m"]) for d in dets])
    min_d = 99.0
    for i in range(len(pts)):
        for j in range(i + 1, len(pts)):
            min_d = min(min_d, float(np.linalg.norm(pts[i] - pts[j])))
    return min_d


def _resolve_target_count(
    session_dets: list[dict],
    cleaned: np.ndarray,
    m_level: float,
    motion_threshold: float,
    max_targets: int,
    expected_count: int | None,
) -> int:
    """Pick final person count — conservative when estimates disagree."""
    recount = estimate_person_count(cleaned, m_level, motion_threshold, max_people=max_targets)
    cluster_n = len(session_dets)

    if expected_count and expected_count > 0:
        if cluster_n > 0 and abs(cluster_n - expected_count) <= 1:
            return min(max_targets, int(np.round((expected_count + cluster_n) / 2)))
        return min(max_targets, expected_count)

    candidates = [x for x in (recount, cluster_n) if x > 0]
    if not candidates:
        return 0
    if len(candidates) == 1:
        return min(max_targets, candidates[0])
    lo, hi = min(candidates), max(candidates)
    if hi - lo >= 2:
        return min(max_targets, lo)
    return min(max_targets, int(np.round(np.median(candidates))))


def _count_svd_sources(s: np.ndarray, svd_ratio: float, max_people: int) -> int:
    """Count motion sources from singular-value energy above noise floor."""
    if len(s) == 0 or s[0] <= 0:
        return 0
    s2 = s.astype(np.float64) ** 2
    total = float(s2.sum())
    if total <= 0:
        return 0
    tail = s2[max(1, len(s2) // 2):]
    noise = float(np.median(tail)) if len(tail) else float(s2[-1])
    floor = max(noise * 4.0, svd_ratio * float(s2[0]))
    n = 0
    cum = 0.0
    for i, e in enumerate(s2[:max_people]):
        if e < floor:
            break
        if i > 0 and e / total < 0.035:
            break
        cum += e
        n = i + 1
        if cum / total > 0.9:
            break
    return n


def _svd_motion_sources_orthogonal(
    csi: np.ndarray,
    n_sources: int,
    svd_ratio: float,
) -> list[np.ndarray]:
    """Iterative SVD with orthogonal residual — separates independent motion sources."""
    phase = np.angle(csi)
    phase = detrend(phase, axis=0, type="linear")
    phase = phase - phase.mean(axis=0, keepdims=True)
    residual = phase.copy()
    sources: list[np.ndarray] = []
    s0 = 0.0

    for _ in range(n_sources):
        if residual.shape[0] < 8:
            break
        try:
            u, s, vh = np.linalg.svd(residual, full_matrices=False)
        except np.linalg.LinAlgError:
            break
        if len(s) == 0 or s[0] <= 0:
            break
        if not sources:
            s0 = float(s[0])
        elif s[0] < svd_ratio * s0:
            break
        comp = (u[:, 0:1] * s[0]) @ vh[0:1, :]
        sources.append(comp)
        residual = residual - comp

    return sources


def _delay_peak_count(cleaned: np.ndarray, gates: dict, max_people: int) -> int:
    """Count spatially separated delay peaks (merged, prominence-ranked)."""
    prof = _delay_profile(cleaned)
    if prof.max() <= 0:
        return 0
    n_sc = cleaned.shape[1] if cleaned.ndim == 2 else len(prof)
    height = gates["peak_ratio"] * prof.max()
    prom = height * 0.22
    min_sep = max(3, len(prof) // 16)
    if n_sc <= 40:
        min_sep = max(4, len(prof) // 6)
        prom = height * 0.35
    peaks, props = find_peaks(
        prof,
        height=height * 0.65,
        distance=min_sep,
        prominence=max(prom, 1e-9),
    )
    if len(peaks) == 0:
        peaks, props = find_peaks(prof, height=height * 0.45, distance=min_sep)
    if len(peaks) == 0:
        return 0
    prominences = props.get("prominences", prof[peaks])
    order = np.argsort(prominences)[::-1]
    selected: list[int] = []
    max_h = float(prof.max())
    for idx in order:
        p = int(peaks[idx])
        h = float(prof[p])
        prom_r = float(prominences[idx]) / max_h
        if h < max_h * gates["peak_ratio"] * 0.75:
            continue
        if prom_r < 0.05:
            continue
        if all(abs(p - s) >= min_sep for s in selected):
            selected.append(p)
        if len(selected) >= max_people:
            break
    return len(selected)


def _delay_peak_count_relaxed(cleaned: np.ndarray, gates: dict, max_people: int) -> int:
    """Secondary delay peak count with relaxed gates for multi-person scenes."""
    prof = _delay_profile(cleaned)
    if prof.max() <= 0:
        return 0
    height = gates["peak_ratio"] * prof.max()
    min_sep = max(2, len(prof) // 20)
    peaks, props = find_peaks(prof, height=height * 0.4, distance=min_sep)
    if len(peaks) == 0:
        return 0
    prominences = props.get("prominences", prof[peaks])
    order = np.argsort(prominences)[::-1]
    max_h = float(prof.max())
    selected: list[int] = []
    for idx in order:
        p = int(peaks[idx])
        if float(prof[p]) < max_h * 0.25:
            continue
        if all(abs(p - s) >= min_sep for s in selected):
            selected.append(p)
        if len(selected) >= max_people:
            break
    return len(selected)


def _band_active_count(cleaned: np.ndarray, max_people: int) -> int:
    """How many subcarrier bands show independent motion."""
    n_sc = cleaned.shape[1]
    if n_sc < 6:
        return 0
    if n_sc <= 40:
        return 0
    n_bands = min(max_people, max(4, n_sc // 4))
    bands = np.array_split(np.arange(n_sc), n_bands)
    amp = np.abs(cleaned)
    band_vars = [float(np.mean(np.var(amp[:, b], axis=1))) for b in bands if len(b) > 1]
    if not band_vars:
        return 0
    med = float(np.median(band_vars))
    thresh = med * 1.08
    return int(np.sum(np.array(band_vars) > thresh))


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

    quality = _motion_signal_quality(cleaned, motion_threshold)
    min_quality = 0.06 if motion_level >= motion_threshold * 2.0 else 0.10
    if quality < min_quality and motion_level < motion_threshold * 1.5:
        return 0

    t_len, n_sc = cleaned.shape
    if t_len < 16 or n_sc < 3:
        return 0

    gates = _narrow_sc_gates(_adaptive_gates(motion_level, motion_threshold), n_sc)

    n_svd = 0
    delay_n = 0
    motion_n = 0
    band_n = 0
    temporal_n = 0

    motion_n = _count_motion_delay_peaks(cleaned, gates, max_people)

    # SVD motion sources — energy above noise floor
    try:
        phase = detrend(np.angle(cleaned), axis=0, type="linear")
        phase -= phase.mean(axis=0, keepdims=True)
        _, s, _ = np.linalg.svd(phase, full_matrices=False)
        svd_cap = min(max_people, max(2, n_sc // 8)) if n_sc <= 40 else max_people
        n_svd = _count_svd_sources(s, gates["svd_ratio"], svd_cap)
    except np.linalg.LinAlgError:
        pass

    # Static delay peaks (secondary for narrow-band CSI)
    delay_n = _delay_peak_count(cleaned, gates, max_people)
    band_n = _band_active_count(cleaned, max_people)
    if delay_n == 0:
        relaxed = _delay_peak_count_relaxed(cleaned, gates, max_people)
        if relaxed > 0:
            delay_n = relaxed

    try:
        mcurve = motion_energy(cleaned)
        if len(mcurve) > 96:
            med = float(np.median(mcurve))
            std = float(np.std(mcurve))
            thresh = med + max(0.55 * std, motion_threshold * 0.35)
            peaks, _ = find_peaks(
                mcurve,
                height=thresh,
                distance=max(48, len(mcurve) // 12),
                prominence=max(0.25 * std, motion_threshold * 0.15),
            )
            if 2 <= len(peaks) <= max_people:
                temporal_n = len(peaks)
    except Exception:
        pass

    parts: list[int] = []
    if motion_n >= 1:
        parts.append(motion_n)
    if delay_n >= 1 and (n_sc > 40 or motion_n == 0):
        parts.append(delay_n)
    if n_svd >= 1 and n_svd <= max(motion_n, delay_n, 1) + 1:
        parts.append(n_svd)
    if band_n >= 2 and band_n <= max(delay_n, n_svd, motion_n, 1) + 1:
        parts.append(band_n)
    if temporal_n >= 2 and temporal_n <= max(delay_n, n_svd, motion_n, band_n, 1) + 1:
        parts.append(temporal_n)

    if not parts:
        return 0

    if n_sc <= 40:
        lo, hi = min(parts), max(parts)
        count = lo if hi - lo >= 2 else int(np.round(np.median(parts)))
    else:
        count = int(np.round(float(np.median(parts))))

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
        mean_phase = _weighted_mean_axis0(phase, w)
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
    n_sc = cleaned.shape[1]
    prof = _delay_profile(cleaned)
    peak_f = _refined_peak_index(prof, int(delay_bin))
    angle = _aoa_enhanced(cleaned, int(round(peak_f)))
    sx, sy = sensor_xy
    r = _range_enhanced(prof, peak_f, n_sc, area_size_m)
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
    orth = _svd_motion_sources_orthogonal(csi, n_sources, svd_ratio)
    if orth:
        return orth
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

    centroids = cluster_xy(
        [(p["x_m"], p["y_m"]) for p in raw_points],
        eps=adaptive_cluster_eps(max_targets, area_size_m),
        max_clusters=max_targets,
    )
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


def _guaranteed_motion_targets(
    cleaned: np.ndarray,
    fs_hz: float,
    area_size_m: float,
    n_targets: int,
    sensor_xy: tuple[float, float],
) -> list[dict]:
    """Last-resort XY placement from motion-heavy subcarrier bands."""
    n_sc = cleaned.shape[1]
    if n_sc < 4 or n_targets <= 0:
        return []

    amp = np.abs(cleaned)
    chunk = max(4, n_sc // 8)
    band_motion: list[tuple[float, float, int]] = []
    step = max(1, chunk // 2)
    for start in range(0, n_sc - chunk + 1, step):
        band = slice(start, start + chunk)
        var_t = float(np.mean(np.var(amp[:, band], axis=1)))
        phase = np.unwrap(np.angle(cleaned[:, band]).mean(axis=0))
        sc = np.arange(len(phase)) + start
        slope = float(np.polyfit(sc, phase, 1)[0]) if len(sc) > 1 else 0.0
        band_motion.append((var_t, slope, start + chunk // 2))

    if not band_motion:
        return []

    band_motion.sort(key=lambda x: -x[0])
    med = float(np.median([b[0] for b in band_motion]))
    sx, sy = sensor_xy
    dets: list[dict] = []

    for var_t, slope, sc_center in band_motion:
        if var_t < med * 0.65 and len(dets) >= 1:
            continue
        angle = float(np.clip(slope * 2.2, -1.1, 1.1))
        r = 1.8 + (sc_center / max(n_sc, 1)) * (area_size_m * 0.65)
        dets.append({
            "x_m": float(np.clip(sx + r * np.sin(angle), 0.8, area_size_m - 0.8)),
            "y_m": float(np.clip(sy + r * np.cos(angle), 0.8, area_size_m - 0.8)),
            "velocity_mps": 0.0,
            "weight": var_t,
            "confidence": var_t,
            "delay_bin": int(sc_center),
            "dt": 1.0 / fs_hz,
        })
        if len(dets) >= n_targets:
            break

    while len(dets) < n_targets:
        break  # never invent synthetic positions — only real CSI sources

    centroids = cluster_xy([(p["x_m"], p["y_m"]) for p in dets], eps=CLUSTER_EPS_M, max_clusters=n_targets)
    merged: list[dict] = []
    for cx, cy in centroids:
        nearby = [p for p in dets if (p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2 < 4.0]
        best = max(nearby, key=lambda p: p.get("weight", 0)) if nearby else dets[0]
        d = dict(best)
        d["x_m"], d["y_m"] = cx, cy
        merged.append(d)
    return merged[:n_targets]


def force_csi_targets(
    cleaned: np.ndarray,
    fs_hz: float,
    area_size_m: float,
    n_targets: int,
    sensor_xy: tuple[float, float],
    motion_level: float,
    motion_threshold: float = 0.02,
) -> list[dict]:
    """
  Guaranteed CSI-only targets when motion is confirmed but strict filters returned nothing.
    """
    if n_targets <= 0 or motion_level < motion_threshold * 0.6:
        return []

    gates = _adaptive_gates(motion_level, motion_threshold)
    relaxed_ratio = gates["peak_ratio"] * 0.45
    raw: list[dict] = []
    raw.extend(_iterative_delay_peaks(
        cleaned, fs_hz, area_size_m, n_targets, sensor_xy, relaxed_ratio
    ))
    raw.extend(_delay_peak_candidates(
        cleaned, fs_hz, area_size_m, n_targets, sensor_xy, relaxed_ratio
    ))
    raw.extend(_band_motion_sources(cleaned, fs_hz, area_size_m, n_targets, sensor_xy))

    for src in _svd_motion_sources(cleaned, n_targets, gates["svd_ratio"] * 0.6):
        det = _localize_from_source(src, fs_hz, area_size_m, sensor_xy)
        if det:
            raw.append(det)

    if not raw:
        return _guaranteed_motion_targets(cleaned, fs_hz, area_size_m, n_targets, sensor_xy)

    centroids = cluster_xy([(p["x_m"], p["y_m"]) for p in raw], eps=CLUSTER_EPS_M, max_clusters=n_targets)
    merged: list[dict] = []
    for cx, cy in centroids:
        nearby = [p for p in raw if (p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2 < 4.0]
        if nearby:
            ws = np.array([p.get("weight", 1.0) for p in nearby], dtype=float)
            ws /= ws.sum() + 1e-9
            cx = float(np.sum([p["x_m"] * w for p, w in zip(nearby, ws)]))
            cy = float(np.sum([p["y_m"] * w for p, w in zip(nearby, ws)]))
            best = max(nearby, key=lambda p: p.get("weight", 0))
        else:
            best = min(raw, key=lambda p: (p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2)
        d = dict(best)
        d["x_m"], d["y_m"] = cx, cy
        d["confidence"] = _score_detection(cleaned, d)
        merged.append(d)

    merged.sort(key=lambda d: -d.get("confidence", d.get("weight", 0)))
    if not merged:
        return _guaranteed_motion_targets(cleaned, fs_hz, area_size_m, n_targets, sensor_xy)
    return merged[:n_targets]


def _refined_peak_index(prof: np.ndarray, peak: int) -> float:
    """Sub-bin parabolic interpolation on delay peak."""
    if peak <= 0 or peak >= len(prof) - 1:
        return float(peak)
    y0, y1, y2 = float(prof[peak - 1]), float(prof[peak]), float(prof[peak + 1])
    denom = y0 - 2.0 * y1 + y2
    if abs(denom) < 1e-12:
        return float(peak)
    return float(peak) + 0.5 * (y0 - y2) / denom


def _aoa_enhanced(csi: np.ndarray, delay_bin: int) -> float:
    """Robust AoA from weighted phase slope across subcarriers near delay peak."""
    if csi.ndim != 2 or csi.shape[1] < 4:
        return 0.0
    n_sc = csi.shape[1]
    lo = max(0, delay_bin - 10)
    hi = min(n_sc, delay_bin + 11)
    seg = csi[:, lo:hi]
    if seg.shape[1] < 4:
        return _subcarrier_angle(csi, delay_bin=delay_bin)

    amp = np.mean(np.abs(seg), axis=0)
    if amp.ndim != 1 or len(amp) < 3:
        return _subcarrier_angle(csi, delay_bin=delay_bin)
    phase = np.angle(seg)
    if phase.shape[1] != len(amp):
        return _subcarrier_angle(csi, delay_bin=delay_bin)
    if phase.shape[0] > 2:
        phase = detrend(phase, axis=0, type="linear")
    w = amp / (float(amp.sum()) + 1e-9)
    mean_phase = _weighted_mean_axis0(phase, w)
    mean_phase = np.unwrap(mean_phase)
    sc = np.arange(len(mean_phase)) + lo

    slopes = []
    for width in (len(sc), max(4, len(sc) // 2)):
        if width < 3:
            continue
        idx = np.argsort(amp)[-width:]
        idx = np.sort(idx)
        if len(idx) < 3:
            continue
        slopes.append(float(np.polyfit(sc[idx], mean_phase[idx], 1)[0]))

    if not slopes:
        return _subcarrier_angle(csi, delay_bin=delay_bin)
    slope = float(np.median(slopes))
    return float(np.clip(slope * 1.85, -1.15, 1.15))


def _range_enhanced(prof: np.ndarray, peak_f: float, n_sc: int, area_size_m: float) -> float:
    """Range from refined delay peak using this recording's delay spread."""
    return _range_from_delay_peak(prof, peak_f, area_size_m)


def _localize_motion_delay_sources(
    cleaned: np.ndarray,
    fs_hz: float,
    area_size_m: float,
    sensor_xy: tuple[float, float],
    max_targets: int,
    peak_ratio: float,
) -> list[dict]:
    """Localize from delay bins with strongest temporal motion (per-dataset)."""
    prof = _motion_delay_profile(cleaned)
    if prof.max() <= 0:
        return []
    n_sc = cleaned.shape[1]
    h_time = np.abs(np.fft.ifft(cleaned, axis=1))
    height = peak_ratio * float(prof.max())
    min_sep = max(4, len(prof) // 7) if n_sc <= 40 else max(3, len(prof) // 14)
    peaks, props = find_peaks(
        prof,
        height=height * 0.45,
        distance=min_sep,
        prominence=max(height * 0.2, float(np.std(prof)) * 0.35),
    )
    if len(peaks) == 0:
        peaks = np.array([int(np.argmax(prof))])
    prominences = props.get("prominences", prof[peaks]) if len(peaks) else prof[peaks]
    order = np.argsort(prominences)[::-1]
    sx, sy = sensor_xy
    dets: list[dict] = []

    for idx in order[:max_targets]:
        peak = int(peaks[idx])
        peak_f = _refined_peak_index(prof, peak)
        bin_series = h_time[:, peak]
        active = bin_series >= np.percentile(bin_series, 65)
        if int(active.sum()) < 8:
            active = np.ones(len(bin_series), dtype=bool)
        seg = cleaned[active]
        angle = _aoa_per_delay_bin(cleaned, peak)
        if abs(angle) < 0.05:
            angle = _aoa_enhanced(seg, peak)
        r = _range_from_delay_peak(prof, peak_f, area_size_m)
        x = float(np.clip(sx + r * np.sin(angle), 0.8, area_size_m - 0.8))
        y = float(np.clip(sy + r * np.cos(angle), 0.8, area_size_m - 0.8))
        dets.append({
            "x_m": x,
            "y_m": y,
            "velocity_mps": 0.0,
            "weight": float(prof[peak]),
            "confidence": float(prof[peak] / (prof.max() + 1e-9)),
            "delay_bin": int(round(peak_f)),
            "dt": 1.0 / fs_hz,
        })
    return dets


def _localize_from_csi_segment(
    seg: np.ndarray,
    fs_hz: float,
    area_size_m: float,
    sensor_xy: tuple[float, float],
    weight: float = 1.0,
) -> dict | None:
    """Localize one motion source from an isolated CSI segment."""
    if seg.ndim != 2 or seg.shape[0] < 8 or seg.shape[1] < 4:
        return None
    prof = _delay_profile(seg)
    if prof.max() <= 0:
        return None
    peak = int(np.argmax(prof))
    peak_f = _refined_peak_index(prof, peak)
    angle = _aoa_per_delay_bin(seg, peak)
    if abs(angle) < 0.05:
        angle = _aoa_enhanced(seg, peak)
    sx, sy = sensor_xy
    r = _range_enhanced(prof, peak_f, seg.shape[1], area_size_m)
    x = float(np.clip(sx + r * np.sin(angle), 0.8, area_size_m - 0.8))
    y = float(np.clip(sy + r * np.cos(angle), 0.8, area_size_m - 0.8))

    sig = detrend(np.abs(seg[:, max(0, peak - 2) : min(seg.shape[1], peak + 3)]).mean(axis=1), type="linear")
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
        "weight": float(weight),
        "confidence": float(weight),
        "delay_bin": int(round(peak_f)),
        "dt": 1.0 / fs_hz,
    }


def localize_motion_sources(
    csi: np.ndarray,
    fs_hz: float,
    area_size_m: float,
    max_targets: int,
    sensor_xy: tuple[float, float],
    skip_srcc: bool = False,
    motion_level: float = 0.0,
    motion_threshold: float = 0.02,
    count_limit: int | None = None,
) -> list[dict]:
    """
    Accurate CSI-only localization via SVD source separation + refined delay/AoA.
    Uses a single calibrated sensor reference (center of search area).
    """
    if skip_srcc:
        cleaned = np.nan_to_num(csi)
    else:
        cleaned = np.nan_to_num(srcc(preprocess_csi(csi)))
    if cleaned.shape[0] < 16 or cleaned.shape[1] < 3:
        return []
    if motion_level < motion_threshold * 0.65:
        return []

    n_sc = cleaned.shape[1]
    gates = _adaptive_gates(motion_level, motion_threshold)
    gates = _narrow_sc_gates(gates, n_sc)
    cap = min(max_targets, count_limit) if count_limit and count_limit > 0 else max_targets
    cap = max(1, int(cap))

    raw: list[dict] = []
    raw.extend(_localize_motion_delay_sources(
        cleaned, fs_hz, area_size_m, sensor_xy, cap, gates["peak_ratio"]
    ))

    seen_bins = [d["delay_bin"] for d in raw]

    # Secondary: SVD-separated sources when motion-delay finds fewer than cap
    if len(raw) < cap:
        sources = _svd_motion_sources(cleaned, cap - len(raw), gates["svd_ratio"])
        for i, src in enumerate(sources):
            pseudo = np.exp(1j * np.angle(src)) * (np.abs(cleaned) + 1e-6)
            det = _localize_from_csi_segment(
                pseudo.astype(np.complex64), fs_hz, area_size_m, sensor_xy,
                weight=float(i + 1) / max(len(sources), 1),
            )
            if det and all(abs(det["delay_bin"] - b) >= 3 for b in seen_bins):
                det["source_id"] = i
                raw.append(det)
                seen_bins.append(det["delay_bin"])

    # Tertiary: static delay peaks not already captured
    prof = _delay_profile(cleaned)
    residual = prof.copy()
    n_bins = len(prof)
    min_sep = max(4, n_bins // 7) if n_sc <= 40 else max(3, n_bins // 16)
    while len(raw) < cap:
        if residual.max() <= 0:
            break
        peak = int(np.argmax(residual))
        if float(prof[peak]) < gates["peak_ratio"] * prof.max():
            break
        if any(abs(peak - b) < min_sep for b in seen_bins):
            lo = max(0, peak - min_sep)
            hi = min(n_bins, peak + min_sep + 1)
            residual[lo:hi] = 0
            continue
        det = _localize_from_csi_segment(
            cleaned, fs_hz, area_size_m, sensor_xy, weight=float(prof[peak])
        )
        if det:
            raw.append(det)
            seen_bins.append(det["delay_bin"])
        lo = max(0, peak - min_sep)
        hi = min(n_bins, peak + min_sep + 1)
        residual[lo:hi] = 0

    if not raw:
        return []

    eps = adaptive_cluster_eps(max(len(raw), 1), area_size_m)
    centroids = cluster_xy([(p["x_m"], p["y_m"]) for p in raw], eps=eps, max_clusters=cap)
    merged: list[dict] = []
    for cx, cy in centroids:
        nearby = [p for p in raw if (p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2 < 2.8]
        if nearby:
            ws = np.array([p.get("confidence", p.get("weight", 1.0)) for p in nearby], dtype=float)
            ws /= ws.sum() + 1e-9
            cx = float(np.sum([p["x_m"] * w for p, w in zip(nearby, ws)]))
            cy = float(np.sum([p["y_m"] * w for p, w in zip(nearby, ws)]))
            best = max(nearby, key=lambda p: p.get("confidence", p.get("weight", 0)))
        else:
            best = min(raw, key=lambda p: (p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2)
        d = dict(best)
        d["x_m"], d["y_m"] = cx, cy
        d["confidence"] = _score_detection(cleaned, d)
        merged.append(d)

    merged.sort(key=lambda d: -d.get("confidence", 0))
    return filter_confident_detections(merged, cleaned, gates["min_score"] * 0.65, cap)


def _stabilize_positions(dets: list[dict], area_size_m: float) -> list[dict]:
    """Snap near-duplicate positions and enforce minimum separation."""
    if len(dets) < 2:
        return dets
    out: list[dict] = []
    used = [False] * len(dets)
    sorted_d = sorted(dets, key=lambda d: -d.get("confidence", d.get("weight", 0)))
    min_sep = max(1.2, area_size_m / 12.0)
    for i, d in enumerate(sorted_d):
        if used[i]:
            continue
        group = [d]
        used[i] = True
        for j in range(i + 1, len(sorted_d)):
            if used[j]:
                continue
            o = sorted_d[j]
            if (d["x_m"] - o["x_m"]) ** 2 + (d["y_m"] - o["y_m"]) ** 2 < min_sep ** 2:
                group.append(o)
                used[j] = True
        ws = np.array([g.get("confidence", g.get("weight", 1.0)) for g in group], dtype=float)
        ws /= ws.sum() + 1e-9
        merged = dict(d)
        merged["x_m"] = float(np.sum([g["x_m"] * w for g, w in zip(group, ws)]))
        merged["y_m"] = float(np.sum([g["y_m"] * w for g, w in zip(group, ws)]))
        merged["confidence"] = float(max(g.get("confidence", 0) for g in group))
        out.append(merged)
    return out


def detect_multinode_targets(
    csi: np.ndarray,
    fs_hz: float,
    area_size_m: float,
    node_positions: dict[int, tuple[float, float]],
    max_targets: int = 6,
    skip_srcc: bool = False,
    motion_level: float = 0.0,
    motion_threshold: float = 0.02,
    count_limit: int | None = None,
) -> list[dict]:
    """Accurate localization from center sensor (node positions used for reference only)."""
    center = (area_size_m / 2.0, 0.0)
    if node_positions:
        xs = [p[0] for p in node_positions.values()]
        ys = [p[1] for p in node_positions.values()]
        center = (float(np.mean(xs)), float(min(ys)))
    return localize_motion_sources(
        csi, fs_hz, area_size_m, max_targets, center,
        skip_srcc=skip_srcc, motion_level=motion_level,
        motion_threshold=motion_threshold, count_limit=count_limit,
    )


def _session_sensor_xy(
    sensor_xy: tuple[float, float],
    area_size_m: float,
    node_positions: dict[int, tuple[float, float]] | None,
) -> tuple[float, float]:
    if not node_positions:
        return sensor_xy
    xs = [p[0] for p in node_positions.values()]
    ys = [p[1] for p in node_positions.values()]
    return (float(np.mean(xs)), float(min(ys)))


def detect_session_targets(
    csi: np.ndarray,
    fs_hz: float,
    area_size_m: float = 10.0,
    max_targets: int = 8,
    sensor_xy: tuple[float, float] = (5.0, 0.0),
    window_sec: float = 0.5,
    motion_threshold: float = 0.02,
    expected_count: int | None = None,
    amplitude_count: int | None = None,
    node_positions: dict[int, tuple[float, float]] | None = None,
) -> list[dict]:
    """Aggregate CSI detections across sliding windows with temporal voting."""
    t_len = len(csi)
    if t_len < 32:
        return []

    raw = preprocess_csi(csi)
    cleaned = np.nan_to_num(srcc(raw))
    raw_motion = float(np.mean(motion_energy(np.nan_to_num(srcc(csi)))))
    motion_level = float(np.mean(motion_energy(cleaned)))
    m_level = max(raw_motion, motion_level)

    if m_level < motion_threshold * 0.60:
        return []

    quality = _motion_signal_quality(cleaned, motion_threshold)
    min_quality = 0.05 if m_level >= motion_threshold * 1.5 else 0.08
    if quality < min_quality and m_level < motion_threshold:
        return []

    estimated = expected_count if expected_count and expected_count > 0 else estimate_person_count(
        cleaned, m_level, motion_threshold, max_people=max_targets
    )
    if amplitude_count is not None and amplitude_count > 0:
        if estimated > 0:
            if abs(amplitude_count - estimated) <= 1:
                estimated = int(np.round((amplitude_count + estimated) / 2))
            else:
                estimated = min(amplitude_count, estimated)
        elif m_level >= motion_threshold * 0.65:
            estimated = amplitude_count

    if estimated <= 0:
        return []

    cluster_cap = int(np.clip(estimated, 1, max_targets))
    cluster_eps = adaptive_cluster_eps(cluster_cap, area_size_m)

    gates = _adaptive_gates(motion_level, motion_threshold)
    win = max(int(window_sec * fs_hz), 48)
    hop = max(win // 4, 16)
    ref_xy = _session_sensor_xy(sensor_xy, area_size_m, node_positions)

    def _localize(chunk: np.ndarray, m_chunk: float) -> list[dict]:
        return localize_motion_sources(
            chunk, fs_hz, area_size_m, max_targets, ref_xy,
            skip_srcc=True, motion_level=m_chunk, motion_threshold=motion_threshold,
            count_limit=cluster_cap,
        )

    window_hits: list[list[dict]] = []
    for start in range(0, max(t_len - win + 1, 1), hop):
        chunk = cleaned[start : start + win]
        m_chunk = float(np.mean(motion_energy(chunk)))
        dets = _localize(chunk, m_chunk)
        if dets:
            window_hits.append(dets)

    full_dets = _localize(cleaned, motion_level)
    if full_dets:
        window_hits.append(full_dets)

    if not window_hits and m_level >= motion_threshold:
        fallback = filter_confident_detections(
            _band_motion_sources(cleaned, fs_hz, area_size_m, cluster_cap, sensor_xy)
            + _delay_peak_candidates(cleaned, fs_hz, area_size_m, cluster_cap, sensor_xy, gates["peak_ratio"] * 0.7),
            cleaned,
            gates["min_score"] * 0.5,
            cluster_cap,
        )
        if fallback:
            return fallback
        return []

    if not window_hits:
        return []

    all_points: list[dict] = [d for group in window_hits for d in group]
    centroids = cluster_xy(
        [(p["x_m"], p["y_m"]) for p in all_points],
        eps=cluster_eps,
        max_clusters=cluster_cap,
    )

    session_dets: list[dict] = []
    min_votes = gates["vote_windows"]
    conf_floor = gates["min_score"] * 1.5
    assign_radius = max(2.2, area_size_m / (max(estimated, 2) * 1.8))

    for cx, cy in centroids:
        nearby = [p for p in all_points if (p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2 < assign_radius ** 2]
        windows_with_hit = sum(
            1 for group in window_hits
            if any((p["x_m"] - cx) ** 2 + (p["y_m"] - cy) ** 2 < assign_radius ** 2 for p in group)
        )
        best = max(nearby, key=lambda p: p.get("confidence", p.get("weight", 0))) if nearby else None
        if best is None:
            continue
        conf = float(best.get("confidence", _score_detection(cleaned, best)))
        if windows_with_hit < min_votes and conf < conf_floor:
            if conf < gates["min_score"] * 0.35:
                continue
        xs = [p["x_m"] for p in nearby]
        ys = [p["y_m"] for p in nearby]
        rx = float(np.median(xs)) if xs else cx
        ry = float(np.median(ys)) if ys else cy
        vel = float(np.median([p["velocity_mps"] for p in nearby])) if nearby else 0.0
        session_dets.append({
            "x_m": rx,
            "y_m": ry,
            "velocity_mps": vel,
            "weight": best.get("weight", 1.0),
            "confidence": conf,
            "delay_bin": best.get("delay_bin", 0),
            "source_id": best.get("source_id", 0),
            "dt": 1.0 / fs_hz,
        })

    session_dets.sort(key=lambda d: -d.get("confidence", 0))
    final_n = _resolve_target_count(
        session_dets, cleaned, m_level, motion_threshold, max_targets, cluster_cap
    )
    session_dets = _stabilize_positions(session_dets, area_size_m)[:final_n]

    if not session_dets and m_level >= motion_threshold:
        return localize_motion_sources(
            cleaned, fs_hz, area_size_m, max_targets, ref_xy,
            skip_srcc=True, motion_level=m_level, motion_threshold=motion_threshold,
            count_limit=cluster_cap,
        )
    return session_dets
