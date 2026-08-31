"""CSI quality metrics and video–CSI sync validation (not person detection)."""

from __future__ import annotations

import hashlib

import numpy as np
from scipy.signal import resample

from .srcc import srcc, motion_energy
from .multitarget import preprocess_csi, _delay_profile


def csi_motion_curve(csi: np.ndarray, n_points: int = 64) -> np.ndarray:
    """Normalized temporal motion-energy curve from CSI."""
    cleaned = np.nan_to_num(srcc(preprocess_csi(csi)))
    curve = motion_energy(cleaned)
    if len(curve) < 4:
        return np.zeros(n_points, dtype=np.float64)
    if len(curve) != n_points:
        curve = resample(curve, n_points)
    curve = curve.astype(np.float64)
    curve -= curve.min()
    mx = curve.max()
    if mx > 0:
        curve /= mx
    return curve


def video_motion_curve(video_path: str, duration_sec: float, n_points: int = 64) -> np.ndarray:
    """Normalized per-segment frame-difference motion from video (sync check only)."""
    try:
        import cv2
    except ImportError:
        return np.zeros(n_points, dtype=np.float64)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return np.zeros(n_points, dtype=np.float64)

    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    scores = np.zeros(n_points, dtype=np.float64)
    counts = np.zeros(n_points, dtype=np.int32)
    prev = None

    for fi in range(n_frames):
        ret, frame = cap.read()
        if not ret:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)
        if prev is not None:
            diff = float(np.mean(cv2.absdiff(gray, prev)))
            t = (fi / max(n_frames - 1, 1)) * duration_sec
            bin_idx = min(int(t / max(duration_sec, 0.1) * n_points), n_points - 1)
            scores[bin_idx] += diff
            counts[bin_idx] += 1
        prev = gray

    cap.release()
    for i in range(n_points):
        if counts[i] > 0:
            scores[i] /= counts[i]
    mx = scores.max()
    if mx > 0:
        scores /= mx
    return scores


def sync_correlation(csi_curve: np.ndarray, video_curve: np.ndarray) -> float:
    """Pearson correlation between CSI and video motion curves (0–1 scale)."""
    if len(csi_curve) != len(video_curve) or len(csi_curve) < 4:
        return 0.0
    a = csi_curve - csi_curve.mean()
    b = video_curve - video_curve.mean()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom < 1e-9:
        return 0.0
    r = float(np.dot(a, b) / denom)
    return float(np.clip((r + 1.0) / 2.0, 0.0, 1.0))


def csi_fingerprint(csi: np.ndarray) -> str:
    """Short stable fingerprint so users can verify different CSI files differ."""
    cleaned = np.nan_to_num(srcc(preprocess_csi(csi)))
    prof = _delay_profile(cleaned)
    mcurve = motion_energy(cleaned)
    payload = np.concatenate([
        prof[: min(32, len(prof))],
        mcurve[:: max(1, len(mcurve) // 32)][:32],
        [float(np.mean(motion_energy(cleaned))), float(np.std(mcurve)), float(len(csi))],
    ]).astype(np.float32).tobytes()
    return hashlib.sha256(payload).hexdigest()[:12]


def detection_confidence(detections: list[dict], motion_level: float, motion_threshold: float) -> float:
    """Overall confidence that CSI contains real, localized motion sources."""
    if not detections:
        return 0.0
    confs = [float(d.get("confidence", d.get("weight", 0))) for d in detections]
    mean_conf = float(np.mean(confs)) if confs else 0.0
    motion_ratio = motion_level / max(motion_threshold, 1e-6)
    motion_factor = float(np.clip(motion_ratio / 3.0, 0.0, 1.0))
    return float(np.clip(mean_conf * 0.75 + motion_factor * 0.25, 0.0, 1.0))


def assess_session(
    csi: np.ndarray,
    video_path: str | None,
    duration_sec: float,
    detections: list[dict],
    motion_level: float,
    motion_threshold: float,
) -> dict:
    """Quality + sync assessment for dashboard warnings."""
    csi_curve = csi_motion_curve(csi)
    video_curve = (
        video_motion_curve(video_path, duration_sec)
        if video_path
        else np.zeros_like(csi_curve)
    )
    sync = sync_correlation(csi_curve, video_curve) if video_path else 1.0
    conf = detection_confidence(detections, motion_level, motion_threshold)

    warnings: list[str] = []
    if video_path and sync < 0.32:
        warnings.append(
            "Video and CSI motion patterns do not match — they may be from different recordings."
        )
    if conf < 0.18 and motion_level >= motion_threshold:
        warnings.append(
            "Low CSI detection confidence — results may be unreliable for this dataset."
        )
    if motion_level < motion_threshold * 0.85:
        warnings.append("Little CSI motion detected — scene may be static or CSI is misaligned.")

    return {
        "csi_fingerprint": csi_fingerprint(csi),
        "sync_score": round(sync, 3),
        "confidence": round(conf, 3),
        "motion_level": round(float(motion_level), 5),
        "warnings": warnings,
        "reliable": conf >= 0.18 and (not video_path or sync >= 0.32),
    }
