"""Fuse scene video with CSI for person count and XY localization in simulation."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class VideoPerson:
    x_m: float
    y_m: float
    confidence: float
    is_moving: bool = False


def detect_people_from_video(
    video_path: str,
    area_size_m: float = 10.0,
    n_samples: int = 9,
) -> tuple[int, list[VideoPerson]]:
    """
    Estimate how many people are in the scene and their approximate floor positions.
    Uses OpenCV HOG on several frames (no extra model download).
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return 0, []

    n_frames = max(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), 1)
    hog = cv2.HOGDescriptor()
    hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

    per_frame: list[list[tuple[float, float, float, float]]] = []
    sample_idx = np.linspace(0, n_frames - 1, min(n_samples, n_frames), dtype=int)

    for idx in sample_idx:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        h, w = frame.shape[:2]
        rects, weights = hog.detectMultiScale(
            frame,
            hitThreshold=0,
            winStride=(8, 8),
            padding=(8, 8),
            scale=1.04,
        )
        people = []
        for (x, y, rw, rh), wt in zip(rects, weights):
            if wt < 0.35:
                continue
            cx = (x + rw * 0.5) / w
            foot_y = min((y + rh) / h, 0.98)
            size_norm = float(np.clip(rw / w, 0.05, 0.55))
            people.append((cx, foot_y, size_norm, float(wt)))
        per_frame.append(people)

    cap.release()
    if not per_frame:
        return 0, []

    counts = [len(p) for p in per_frame]
    person_count = int(max(counts)) if counts else 0
    if person_count == 0:
        return 0, []

    # Collect detections from frames with the highest count
    best_frames = [p for p in per_frame if len(p) == person_count]
    pool = best_frames if best_frames else per_frame
    flat = [det for frame in pool for det in frame]
    if not flat:
        return person_count, []

    pts = np.array([[d[0], d[1]] for d in flat])
    used = np.zeros(len(pts), dtype=bool)
    clusters: list[tuple[float, float, float, float]] = []
    for i in range(len(pts)):
        if used[i]:
            continue
        dist = np.linalg.norm(pts - pts[i], axis=1)
        mask = dist < 0.12
        used[mask] = True
        group = [flat[j] for j in np.where(mask)[0]]
        cx = float(np.mean([g[0] for g in group]))
        cy = float(np.mean([g[1] for g in group]))
        sz = float(np.mean([g[2] for g in group]))
        conf = float(np.mean([g[3] for g in group]))
        clusters.append((cx, cy, sz, conf))

    clusters.sort(key=lambda c: -c[3])
    people: list[VideoPerson] = []
    for cx, cy, sz, conf in clusters[:person_count]:
        people.append(_video_norm_to_xy(cx, cy, sz, area_size_m, conf))

    return person_count, people


def _video_norm_to_xy(
    cx: float,
    foot_y: float,
    size_norm: float,
    area_size_m: float,
    confidence: float,
) -> VideoPerson:
    """Map normalized video coords to room meters (sensor at bottom-center)."""
    x_m = float(np.clip(cx * area_size_m, 0.8, area_size_m - 0.8))
    # Larger bbox → closer to camera (bottom of frame) → smaller Y in room map
    depth = 1.0 - size_norm * 1.6
    y_m = float(np.clip(foot_y * area_size_m * depth + 1.2, 0.8, area_size_m - 0.8))
    return VideoPerson(x_m=x_m, y_m=y_m, confidence=confidence)


def video_people_to_detections(
    people: list[VideoPerson],
    fs_hz: float,
) -> list[dict]:
    return [
        {
            "x_m": p.x_m,
            "y_m": p.y_m,
            "velocity_mps": 0.15 if p.is_moving else 0.0,
            "weight": p.confidence,
            "delay_bin": i * 4,
            "dt": 1.0 / fs_hz,
        }
        for i, p in enumerate(people)
    ]


def fuse_csi_and_video(
    csi_detections: list[dict],
    video_people: list[VideoPerson],
    area_size_m: float,
    max_targets: int = 3,
    fs_hz: float = 20.0,
) -> list[dict]:
    """
    Prefer CSI positions when present; fill missing people from video layout.
    """
    if not video_people and csi_detections:
        return csi_detections[:max_targets]
    if not csi_detections and video_people:
        return video_people_to_detections(video_people, fs_hz=fs_hz)[:max_targets]

    merged: list[dict] = []
    used_video = set()

    for cd in csi_detections[:max_targets]:
        best_v = None
        best_d = 4.0
        for i, vp in enumerate(video_people):
            if i in used_video:
                continue
            d = (cd["x_m"] - vp.x_m) ** 2 + (cd["y_m"] - vp.y_m) ** 2
            if d < best_d:
                best_d = d
                best_v = i
        if best_v is not None and best_d < 6.0:
            used_video.add(best_v)
            vp = video_people[best_v]
            merged.append({
                **cd,
                "x_m": float(0.65 * cd["x_m"] + 0.35 * vp.x_m),
                "y_m": float(0.65 * cd["y_m"] + 0.35 * vp.y_m),
            })
        else:
            merged.append(cd)

    for i, vp in enumerate(video_people):
        if i in used_video or len(merged) >= max_targets:
            continue
        merged.append({
            "x_m": vp.x_m,
            "y_m": vp.y_m,
            "velocity_mps": 0.0,
            "weight": vp.confidence,
            "delay_bin": len(merged) * 4,
            "dt": 0.05,
        })

    return merged[:max_targets]
