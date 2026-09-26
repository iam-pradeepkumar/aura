"""sensing_v2 adapter — drop-in replacement for process_hardware_window.

Informed by techniques described across wifi-densepose-mat, spatial-ai,
espressif/esp-csi, and ESP32-Realtime-System, reimplemented for ESP32 CSI in AURA.
"""

from __future__ import annotations

import numpy as np

from ..csi_quality import detection_confidence
from ..doppler import delay_doppler_map
from ..hardware_fusion import inside_search_area
from ..hardware_localize import refine_detection_xy
from ..hardware_sensing import (
    _detections_to_targets,
    _filter_area,
    _hw_threshold,
    _motion_sector_estimate,
)
from ..multitarget import _motion_signal_quality, localize_motion_sources, preprocess_csi
from ..pipeline import SensingResult
from ..srcc import motion_energy, srcc
from .localize import estimate_depth_band
from .motion import motion_score_v2, update_motion_baseline
from .preprocess import preprocess_csi_v2
from .vitals_ensemble import extract_vitals_ensemble


def process_hardware_window_v2(
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
    v2_config: dict | None = None,
    motion_fsm=None,
    motion_baseline: float | None = None,
) -> tuple[SensingResult, dict]:
    """Per-node v2 window processing. Returns (SensingResult, sidecar dict)."""
    cfg = v2_config or {}
    gain_comp = bool(cfg.get("gain_compensation", True))
    sc_weight = bool(cfg.get("subcarrier_weighting", True))
    debounce = int(cfg.get("motion_debounce_frames", 3))
    depth_enabled = bool(cfg.get("depth_band_estimate", False))

    csi, _meta = preprocess_csi_v2(
        csi,
        gain_compensation=gain_comp,
        subcarrier_weighting=sc_weight,
    )
    sensor_xy = sensor_xy or pipeline.node_positions.get(node_id, pipeline.sensor_xy)
    scale = getattr(pipeline, "_hw_motion_scale", 1.0)
    eff_threshold = _hw_threshold(pipeline.motion_threshold, scale)
    motion_min = float(getattr(pipeline, "_hw_motion_min", 0.58))
    indoor = bool(getattr(pipeline, "_hw_indoor_mode", False))

    if motion_info is None:
        motion_info = motion_score_v2(
            csi,
            rssi,
            baseline=motion_baseline,
            motion_min=motion_min,
            indoor_mode=indoor,
            debounce_frames=debounce,
            fsm=motion_fsm,
        )

    score = float(motion_info.get("score", 0))
    motion = bool(motion_info.get("motion"))
    stability = float(motion_info.get("stability", 0.5))

    prepared = preprocess_csi(csi)
    cleaned = np.nan_to_num(srcc(prepared))
    m_energy = float(motion_info.get("energy", np.mean(motion_energy(cleaned))))
    strong_motion = motion and score >= motion_min * (0.82 if indoor else 0.88)
    quality = _motion_signal_quality(cleaned, eff_threshold)

    vcsi_raw = vitals_csi if vitals_csi is not None and len(vitals_csi) >= 16 else csi
    vcsi, _ = preprocess_csi_v2(
        vcsi_raw,
        gain_compensation=gain_comp,
        subcarrier_weighting=sc_weight,
    )
    vprepared = preprocess_csi(vcsi)
    vcleaned = np.nan_to_num(srcc(vprepared))

    quality_gate = 0.05 if indoor else (0.06 if score >= motion_min * 1.05 else 0.07)
    energy_gate = eff_threshold * (0.38 if indoor else (0.48 if score >= motion_min * 1.0 else 0.55))

    sidecar = {
        "motion_info": motion_info,
        "motion_baseline": motion_baseline,
        "stability": stability,
    }

    if not strong_motion or quality < quality_gate or m_energy < energy_gate:
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
        ), sidecar

    cap = min(pipeline.max_targets, max_per_node)
    loc_threshold = eff_threshold * (0.65 if indoor else 0.72)
    window_dets = localize_motion_sources(
        cleaned,
        pipeline.fs_hz,
        pipeline.area_size_m,
        cap,
        sensor_xy,
        skip_srcc=True,
        motion_level=m_energy,
        motion_threshold=loc_threshold,
        count_limit=cap,
    )
    window_dets = [
        refine_detection_xy(d, sensor_xy, pipeline.area_size_m, area_margin_m)
        for d in window_dets
    ]
    window_dets = _filter_area(window_dets, pipeline.area_size_m, area_margin_m)

    allow_fallback = bool(getattr(pipeline, "_hw_allow_sector_fallback", False))
    if not window_dets and allow_fallback and score >= motion_min * (1.0 if indoor else 1.2):
        window_dets = [
            refine_detection_xy(
                _motion_sector_estimate(sensor_xy, pipeline.area_size_m, area_margin_m, m_energy, eff_threshold),
                sensor_xy,
                pipeline.area_size_m,
                area_margin_m,
            )
        ]

    detections = [d for d in window_dets if float(d.get("confidence", 0.5)) >= min_confidence * 0.82]
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
            delay_doppler_map=None,
            events=[],
            confidence=conf,
        ), sidecar

    rssi_med = float(np.median(rssi[-8:])) if rssi is not None and len(rssi) else None
    multipath = float(motion_info.get("jitter", 0.0))

    for det in detections:
        vel = float(det.get("velocity_mps", 0))
        vitals = extract_vitals_ensemble(vcleaned, pipeline.fs_hz, stability, vel)
        det["respiration_bpm"] = vitals.resp_bpm
        det["heartbeat_bpm"] = vitals.hr_bpm
        det["resp_confidence"] = vitals.resp_confidence
        det["hr_confidence"] = vitals.hr_confidence
        det["vitals_quality"] = vitals.quality
        det["respiration_waveform"] = vitals.respiration_waveform
        det["heartbeat_waveform"] = vitals.heartbeat_waveform
        det["source_node"] = node_id
        det["confidence"] = max(float(det.get("confidence", 0.4)), conf)
        det["is_moving"] = strong_motion or vel > 0.12
        if det.get("velocity_mps", 0) < 0.12 and strong_motion:
            det["velocity_mps"] = 0.2
        det["depth_band"] = estimate_depth_band(rssi_med, multipath, depth_enabled)

    _, _, ddm = delay_doppler_map(cleaned, pipeline.fs_hz)
    display_targets = _detections_to_targets(detections)

    r_vals = [t.respiration_bpm for t in display_targets if t.respiration_bpm > 0]
    h_vals = [t.heartbeat_bpm for t in display_targets if t.heartbeat_bpm > 0]

    best_resp_wf = None
    for t in display_targets:
        if t.respiration_waveform is not None and len(t.respiration_waveform):
            best_resp_wf = t.respiration_waveform
            break

    resp_out = best_resp_wf
    hr_out = display_targets[0].heartbeat_waveform if display_targets else None

    result = SensingResult(
        timestamp_sec=timestamp_sec,
        motion_detected=strong_motion and bool(detections),
        motion_energy=m_energy,
        target_count=len(detections),
        targets=display_targets,
        respiration_bpm=float(np.median(r_vals)) if r_vals else 0.0,
        heartbeat_bpm=float(np.median(h_vals)) if h_vals else 0.0,
        respiration_waveform=resp_out,
        heartbeat_waveform=hr_out,
        delay_doppler_map=ddm,
        events=[],
        confidence=conf,
    )
    sidecar["detections_extra"] = detections
    return result, sidecar
