"""Live hardware sensing — per-node geometry for outdoor disaster deployment."""

from __future__ import annotations

import numpy as np

from .csi_quality import detection_confidence
from .doppler import delay_doppler_map
from .hardware_csi import normalize_esp32_csi
from .localization import Target
from .multitarget import (
    detect_session_targets,
    estimate_person_count,
    localize_motion_sources,
    preprocess_csi,
)
from .pipeline import SensingResult
from .srcc import motion_energy, srcc
from .vitals import extract_vitals, extract_vitals_for_detections


def detect_hardware_session_targets(
    csi: np.ndarray,
    fs_hz: float,
    area_size_m: float,
    max_targets: int,
    sensor_xy: tuple[float, float],
    motion_threshold: float = 0.02,
) -> list[dict]:
    """Session-level targets from one ESP32 node's viewpoint (no centroid override)."""
    csi = normalize_esp32_csi(csi)
    prepared = np.nan_to_num(srcc(preprocess_csi(csi)))
    motion_level = float(np.mean(motion_energy(prepared)))

    # Outdoor: slightly lower bar when motion is present but noisy
    eff_threshold = motion_threshold * 0.85

    dets = detect_session_targets(
        csi,
        fs_hz,
        area_size_m,
        max_targets,
        sensor_xy=sensor_xy,
        motion_threshold=eff_threshold,
        node_positions=None,
    )
    if dets:
        return dets

    if motion_level < eff_threshold * 0.4:
        return []

    count = estimate_person_count(prepared, motion_level, eff_threshold, max_people=max_targets)
    if count <= 0 and motion_level >= eff_threshold:
        count = 1

    return localize_motion_sources(
        prepared,
        fs_hz,
        area_size_m,
        max_targets,
        sensor_xy,
        skip_srcc=True,
        motion_level=motion_level,
        motion_threshold=eff_threshold,
        count_limit=count if count > 0 else None,
    )


def process_hardware_window(
    pipeline,
    csi: np.ndarray,
    timestamp_sec: float,
    node_id: int,
) -> SensingResult:
    """Per-node window processing using the receiving ESP32 position."""
    csi = normalize_esp32_csi(csi)
    sensor_xy = pipeline.node_positions.get(node_id, pipeline.sensor_xy)
    eff_threshold = pipeline.motion_threshold * 0.85

    prepared = preprocess_csi(csi)
    cleaned = np.nan_to_num(srcc(prepared))
    m_energy = float(np.mean(motion_energy(cleaned)))
    motion = m_energy > eff_threshold

    vitals = extract_vitals(cleaned, pipeline.fs_hz)
    _, _, ddm = delay_doppler_map(cleaned, pipeline.fs_hz)

    session = pipeline._session_targets
    if not motion and not session:
        return SensingResult(
            timestamp_sec=timestamp_sec,
            motion_detected=False,
            motion_energy=m_energy,
            target_count=0,
            targets=[],
            respiration_bpm=vitals["respiration_bpm"],
            heartbeat_bpm=vitals["heartbeat_bpm"],
            respiration_waveform=vitals["respiration_waveform"],
            heartbeat_waveform=vitals["heartbeat_waveform"],
            delay_doppler_map=ddm,
            events=list(pipeline.tracker.events),
            confidence=0.0,
        )

    count_limit = len(session) if session else None
    window_dets = localize_motion_sources(
        cleaned,
        pipeline.fs_hz,
        pipeline.area_size_m,
        pipeline.max_targets,
        sensor_xy,
        skip_srcc=True,
        motion_level=m_energy,
        motion_threshold=eff_threshold,
        count_limit=count_limit,
    )

    detections = _merge_session_and_window(session, window_dets)
    conf = detection_confidence(detections, m_energy, eff_threshold)
    if conf < 0.05 and not session and m_energy < eff_threshold * 0.5:
        detections = []

    per_vitals = extract_vitals_for_detections(cleaned, pipeline.fs_hz, detections)
    for i, det in enumerate(detections):
        tv = per_vitals[i] if i < len(per_vitals) else {}
        if det.get("respiration_bpm", 0) <= 0:
            det["respiration_bpm"] = tv.get("respiration_bpm", 0.0)
        if det.get("heartbeat_bpm", 0) <= 0:
            det["heartbeat_bpm"] = tv.get("heartbeat_bpm", 0.0)
        det["respiration_waveform"] = tv.get("respiration_waveform")
        det["heartbeat_waveform"] = tv.get("heartbeat_waveform")
        det["source_node"] = node_id
        if det.get("velocity_mps", 0) < 0.12:
            det["velocity_mps"] = 0.0

    targets = pipeline.tracker.update(detections, timestamp_sec)
    display_targets = _display_targets(detections, targets)

    r_vals = [t.respiration_bpm for t in display_targets if t.respiration_bpm > 0]
    h_vals = [t.heartbeat_bpm for t in display_targets if t.heartbeat_bpm > 0]

    return SensingResult(
        timestamp_sec=timestamp_sec,
        motion_detected=motion or bool(session),
        motion_energy=m_energy,
        target_count=len(session) if session else len(detections),
        targets=display_targets,
        respiration_bpm=float(np.median(r_vals)) if r_vals else vitals["respiration_bpm"],
        heartbeat_bpm=float(np.median(h_vals)) if h_vals else vitals["heartbeat_bpm"],
        respiration_waveform=None,
        heartbeat_waveform=None,
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
            if np.hypot(best["x_m"] - s["x_m"], best["y_m"] - s["y_m"]) < 2.8:
                d["velocity_mps"] = max(d.get("velocity_mps", 0.0), best.get("velocity_mps", 0.0))
        merged.append(d)
    return merged


def _display_targets(detections: list[dict], targets: list[Target]) -> list[Target]:
    display: list[Target] = []
    for det in detections:
        best = None
        best_d = 2.0
        for t in targets:
            d = np.hypot(t.x_m - det["x_m"], t.y_m - det["y_m"])
            if d < best_d:
                best_d = d
                best = t
        if best and best not in display:
            best.is_moving = det.get("velocity_mps", 0) > 0.12
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
                    is_moving=det.get("velocity_mps", 0) > 0.12,
                )
            )
    return display
