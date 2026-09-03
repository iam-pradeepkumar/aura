"""Live hardware sensing — per-node geometry for outdoor disaster deployment."""

from __future__ import annotations

import numpy as np

from .csi_quality import detection_confidence
from .doppler import delay_doppler_map
from .hardware_csi import normalize_esp32_csi
from .hardware_fusion import inside_search_area
from .localization import Target
from .multitarget import (
    _motion_signal_quality,
    detect_session_targets,
    estimate_person_count,
    localize_motion_sources,
    preprocess_csi,
)
from .pipeline import SensingResult
from .srcc import motion_energy, srcc
from .vitals import extract_vitals, extract_vitals_for_detections


def _hw_threshold(base: float, scale: float) -> float:
    return base * scale


def _filter_area(dets: list[dict], area_size_m: float, margin_m: float) -> list[dict]:
    return [
        d for d in dets
        if inside_search_area(float(d["x_m"]), float(d["y_m"]), area_size_m, margin_m)
    ]


def _motion_sector_estimate(
    sensor_xy: tuple[float, float],
    area_size_m: float,
    margin_m: float,
    motion_level: float,
    threshold: float,
) -> dict:
    """Fallback XY when CSI localization is weak but motion is present."""
    sx, sy = sensor_xy
    cx, cy = area_size_m / 2.0, area_size_m / 2.0
    strength = float(np.clip(motion_level / max(threshold, 1e-6), 0.35, 1.4))
    alpha = 0.42 + 0.18 * min(strength, 1.0)
    x = sx + alpha * (cx - sx)
    y = sy + alpha * (cy - sy)
    m = max(0.0, margin_m)
    x = float(np.clip(x, m, area_size_m - m))
    y = float(np.clip(y, m, area_size_m - m))
    conf = float(np.clip(0.28 + 0.22 * min(strength, 1.0), 0.28, 0.62))
    return {
        "x_m": x,
        "y_m": y,
        "velocity_mps": 0.25 if strength > 0.8 else 0.12,
        "confidence": conf,
        "is_moving": strength > 0.75,
    }


def detect_hardware_session_targets(
    csi: np.ndarray,
    fs_hz: float,
    area_size_m: float,
    max_targets: int,
    sensor_xy: tuple[float, float],
    motion_threshold: float = 0.02,
    area_margin_m: float = 0.4,
    max_per_node: int = 2,
    motion_score: float = 0.0,
    force_motion: bool = False,
) -> list[dict]:
    """Session-level targets from one ESP32 — tuned for live field CSI."""
    csi = normalize_esp32_csi(csi)
    prepared = np.nan_to_num(srcc(preprocess_csi(csi)))
    motion_level = float(np.mean(motion_energy(prepared)))

    cap = min(max_targets, max_per_node, 2)
    if not force_motion and motion_level < motion_threshold * 0.45 and motion_score < 0.45:
        return []

    quality = _motion_signal_quality(prepared, motion_threshold)
    if quality < 0.08 and motion_level < motion_threshold * 0.85 and not force_motion and motion_score < 0.55:
        return []

    dets = detect_session_targets(
        csi,
        fs_hz,
        area_size_m,
        cap,
        sensor_xy=sensor_xy,
        motion_threshold=motion_threshold * 0.85,
        node_positions=None,
    )
    dets = _filter_area(dets, area_size_m, area_margin_m)
    if dets:
        return dets[:cap]

    count = estimate_person_count(prepared, motion_level, motion_threshold * 0.85, max_people=cap)
    count = int(np.clip(count, 0, cap))
    if count <= 0 and motion_level >= motion_threshold * 0.55:
        count = 1

    if count <= 0:
        return []

    dets = localize_motion_sources(
        prepared,
        fs_hz,
        area_size_m,
        cap,
        sensor_xy,
        skip_srcc=True,
        motion_level=motion_level,
        motion_threshold=motion_threshold * 0.75,
        count_limit=count,
    )
    dets = _filter_area(dets, area_size_m, area_margin_m)
    if not dets and motion_level >= motion_threshold * 0.55:
        dets = [_motion_sector_estimate(sensor_xy, area_size_m, area_margin_m, motion_level, motion_threshold)]
    return dets[:cap]


def process_hardware_window(
    pipeline,
    csi: np.ndarray,
    timestamp_sec: float,
    node_id: int,
    vitals_csi: np.ndarray | None = None,
    rssi: np.ndarray | None = None,
    area_margin_m: float = 0.4,
    max_per_node: int = 2,
    min_confidence: float = 0.28,
    motion_info: dict | None = None,
    sensor_xy: tuple[float, float] | None = None,
) -> SensingResult:
    """Per-node window processing using the receiving ESP32 position."""
    from .hardware_motion import esp32_motion_score

    from .hardware_localize import refine_detection_xy

    csi = normalize_esp32_csi(csi)
    sensor_xy = sensor_xy or pipeline.node_positions.get(node_id, pipeline.sensor_xy)
    scale = getattr(pipeline, "_hw_motion_scale", 1.0)
    eff_threshold = _hw_threshold(pipeline.motion_threshold, scale)

    if motion_info is None:
        motion_info = esp32_motion_score(csi, rssi)

    score = float(motion_info.get("score", 0))
    motion = bool(motion_info.get("motion"))
    motion_min = float(getattr(pipeline, "_hw_motion_min", 0.58))

    prepared = preprocess_csi(csi)
    cleaned = np.nan_to_num(srcc(prepared))
    m_energy = float(motion_info.get("energy", np.mean(motion_energy(cleaned))))
    strong_motion = motion and score >= motion_min * 0.92
    quality = _motion_signal_quality(cleaned, eff_threshold)

    vcsi = normalize_esp32_csi(vitals_csi if vitals_csi is not None and len(vitals_csi) >= 16 else csi)
    vprepared = preprocess_csi(vcsi)
    vcleaned = np.nan_to_num(srcc(vprepared))

    if not strong_motion or quality < 0.07 or m_energy < eff_threshold * 0.55:
        return SensingResult(
            timestamp_sec=timestamp_sec,
            motion_detected=False,
            motion_energy=m_energy,
            target_count=0,
            targets=[],
            respiration_bpm=0.0,
            heartbeat_bpm=0.0,
            respiration_waveform=None,
            heartbeat_waveform=None,
            delay_doppler_map=None,
            events=list(pipeline.tracker.events),
            confidence=0.0,
        )

    vitals = extract_vitals(vcleaned, pipeline.fs_hz, motion_cutoff_hz=1.2)
    _, _, ddm = delay_doppler_map(cleaned, pipeline.fs_hz)

    cap = min(pipeline.max_targets, max_per_node, 2)
    count_limit = cap
    loc_threshold = eff_threshold * 0.72
    window_dets = localize_motion_sources(
        cleaned,
        pipeline.fs_hz,
        pipeline.area_size_m,
        cap,
        sensor_xy,
        skip_srcc=True,
        motion_level=m_energy,
        motion_threshold=loc_threshold,
        count_limit=count_limit,
    )
    window_dets = [
        refine_detection_xy(d, sensor_xy, pipeline.area_size_m, area_margin_m)
        for d in window_dets
    ]
    window_dets = _filter_area(window_dets, pipeline.area_size_m, area_margin_m)

    allow_fallback = bool(getattr(pipeline, "_hw_allow_sector_fallback", False))
    if not window_dets and allow_fallback and score >= motion_min * 1.2:
        window_dets = [
            refine_detection_xy(
                _motion_sector_estimate(sensor_xy, pipeline.area_size_m, area_margin_m, m_energy, eff_threshold),
                sensor_xy,
                pipeline.area_size_m,
                area_margin_m,
            )
        ]

    # Live mode: use current window only (no stale session merge)
    detections = window_dets
    detections = [d for d in detections if float(d.get("confidence", 0.5)) >= min_confidence * 0.82]
    detections = _filter_area(detections, pipeline.area_size_m, area_margin_m)[:cap]

    conf = detection_confidence(detections, m_energy, eff_threshold)

    if not detections:
        return SensingResult(
            timestamp_sec=timestamp_sec,
            motion_detected=strong_motion,
            motion_energy=m_energy,
            target_count=0,
            targets=[],
            respiration_bpm=0.0,
            heartbeat_bpm=0.0,
            respiration_waveform=None,
            heartbeat_waveform=None,
            delay_doppler_map=ddm,
            events=list(pipeline.tracker.events),
            confidence=conf,
        )

    per_vitals = extract_vitals_for_detections(vcleaned, pipeline.fs_hz, detections)
    for i, det in enumerate(detections):
        tv = per_vitals[i] if i < len(per_vitals) else {}
        if det.get("respiration_bpm", 0) <= 0:
            det["respiration_bpm"] = tv.get("respiration_bpm", 0.0)
        if det.get("heartbeat_bpm", 0) <= 0:
            det["heartbeat_bpm"] = tv.get("heartbeat_bpm", 0.0)
        det["respiration_waveform"] = tv.get("respiration_waveform")
        if det["respiration_waveform"] is None:
            det["respiration_waveform"] = vitals.get("respiration_waveform")
        det["heartbeat_waveform"] = tv.get("heartbeat_waveform")
        if det["heartbeat_waveform"] is None:
            det["heartbeat_waveform"] = vitals.get("heartbeat_waveform")
        det["source_node"] = node_id
        det["confidence"] = max(float(det.get("confidence", 0.4)), conf)
        det["is_moving"] = strong_motion or float(det.get("velocity_mps", 0)) > 0.12
        if det.get("velocity_mps", 0) < 0.12 and strong_motion:
            det["velocity_mps"] = 0.2

    targets = pipeline.tracker.update(detections, timestamp_sec)
    display_targets = _display_targets(detections, targets)

    r_vals = [t.respiration_bpm for t in display_targets if t.respiration_bpm > 0]
    h_vals = [t.heartbeat_bpm for t in display_targets if t.heartbeat_bpm > 0]

    best_resp_wf = vitals.get("respiration_waveform")
    if best_resp_wf is None:
        best_resp_wf = []
    best_hr_wf = vitals.get("heartbeat_waveform")
    if best_hr_wf is None:
        best_hr_wf = []
    for t in display_targets:
        if t.respiration_waveform is not None and len(t.respiration_waveform):
            best_resp_wf = t.respiration_waveform
            break

    resp_out = best_resp_wf if best_resp_wf is not None and len(best_resp_wf) else vitals.get("respiration_waveform")
    hr_out = best_hr_wf if best_hr_wf is not None and len(best_hr_wf) else vitals.get("heartbeat_waveform")

    return SensingResult(
        timestamp_sec=timestamp_sec,
        motion_detected=strong_motion and bool(detections),
        motion_energy=m_energy,
        target_count=len(detections),
        targets=display_targets,
        respiration_bpm=float(np.median(r_vals)) if r_vals else vitals["respiration_bpm"],
        heartbeat_bpm=float(np.median(h_vals)) if h_vals else vitals["heartbeat_bpm"],
        respiration_waveform=resp_out,
        heartbeat_waveform=hr_out,
        delay_doppler_map=ddm,
        events=list(pipeline.tracker.events),
        confidence=conf,
    )


def _merge_session_and_window(session: list[dict], window_dets: list[dict]) -> list[dict]:
    if not session:
        return window_dets
    merged: list[dict] = []
    for s in session:
        d = dict(s)
        if window_dets:
            best = min(
                window_dets,
                key=lambda w: np.hypot(w["x_m"] - s["x_m"], w["y_m"] - s["y_m"]),
            )
            if np.hypot(best["x_m"] - s["x_m"], best["y_m"] - s["y_m"]) < 3.5:
                d["velocity_mps"] = max(d.get("velocity_mps", 0.0), best.get("velocity_mps", 0.0))
                d["confidence"] = max(float(d.get("confidence", 0)), float(best.get("confidence", 0)))
                d["is_moving"] = d.get("is_moving") or best.get("is_moving")
        merged.append(d)
    return merged


def _display_targets(detections: list[dict], targets: list[Target]) -> list[Target]:
    display: list[Target] = []
    for det in detections:
        best = None
        best_d = 2.5
        for t in targets:
            d = np.hypot(t.x_m - det["x_m"], t.y_m - det["y_m"])
            if d < best_d:
                best_d = d
                best = t
        if best and best not in display:
            best.is_moving = det.get("is_moving") or det.get("velocity_mps", 0) > 0.12
            best.respiration_bpm = det.get("respiration_bpm", best.respiration_bpm)
            best.heartbeat_bpm = det.get("heartbeat_bpm", best.heartbeat_bpm)
            best.respiration_waveform = det.get("respiration_waveform", best.respiration_waveform)
            best.heartbeat_waveform = det.get("heartbeat_waveform", best.heartbeat_waveform)
            display.append(best)
        else:
            display.append(
                Target(
                    id=len(display) + 1,
                    x_m=det["x_m"],
                    y_m=det["y_m"],
                    velocity_mps=det.get("velocity_mps", 0),
                    respiration_bpm=det.get("respiration_bpm", 0),
                    heartbeat_bpm=det.get("heartbeat_bpm", 0),
                    respiration_waveform=det.get("respiration_waveform"),
                    heartbeat_waveform=det.get("heartbeat_waveform"),
                    is_moving=det.get("is_moving") or det.get("velocity_mps", 0) > 0.12,
                )
            )
    return display
