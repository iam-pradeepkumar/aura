"""Persistent CSI buffers and pipelines for live ESP32 hardware."""

from __future__ import annotations

import numpy as np

from .hardware_motion import esp32_motion_score, update_baseline
from .hardware_sensing import detect_hardware_session_targets, process_hardware_window
from .pipeline import AURAPipeline


def estimate_fs_hz(timestamps_ms: np.ndarray) -> float:
    if len(timestamps_ms) < 2:
        return 20.0
    dt = np.diff(timestamps_ms)
    dt = dt[(dt > 0) & (dt < 2000)]
    if len(dt) == 0:
        return 20.0
    return float(1000.0 / max(np.median(dt), 1.0))


class NodePipelineState:
    """Per-node CSI accumulation + outdoor field sensing from ESP32 position."""

    def __init__(
        self,
        node_id: int,
        pipeline: AURAPipeline,
        min_packets: int = 80,
        refresh_every: int = 40,
        motion_threshold_scale: float = 0.85,
        vitals_packets: int = 100,
        area_margin_m: float = 0.6,
        max_per_node: int = 2,
        min_confidence: float = 0.35,
    ):
        self.node_id = node_id
        self.pipeline = pipeline
        self.min_packets = min_packets
        self.refresh_every = refresh_every
        self.motion_threshold_scale = motion_threshold_scale
        self.vitals_packets = vitals_packets
        self.area_margin_m = area_margin_m
        self.max_per_node = max_per_node
        self.min_confidence = min_confidence
        self._packet_count = 0
        self._motion_baseline: float | None = None
        self._last_motion_score = 0.0
        self._sensor_xy = pipeline.node_positions.get(node_id, pipeline.sensor_xy)
        self.pipeline._hw_motion_scale = motion_threshold_scale

    def process(self, csi: np.ndarray, timestamps_ms: np.ndarray, rssi: np.ndarray | None = None):
        n = len(csi)
        if n < self.min_packets:
            return None

        fs = estimate_fs_hz(timestamps_ms)
        self.pipeline.fs_hz = fs
        self.pipeline.window_samples = max(self.min_packets, min(int(2.5 * fs), n))

        motion_info = esp32_motion_score(csi, rssi, baseline=self._motion_baseline)
        self._last_motion_score = motion_info["score"]
        if not motion_info["motion"]:
            self._motion_baseline = update_baseline(self._motion_baseline, motion_info["score"])

        self._packet_count += 1
        eff_threshold = self.pipeline.motion_threshold * self.motion_threshold_scale
        if self._packet_count == 1 or self._packet_count % self.refresh_every == 0:
            self.pipeline._session_targets = detect_hardware_session_targets(
                csi,
                fs,
                self.pipeline.area_size_m,
                self.pipeline.max_targets,
                self._sensor_xy,
                motion_threshold=eff_threshold,
                area_margin_m=self.area_margin_m,
                max_per_node=self.max_per_node,
                motion_score=motion_info["score"],
                force_motion=motion_info["motion"],
            )
            self.pipeline.estimated_person_count = len(self.pipeline._session_targets)
            self.pipeline.session_confidence = max(
                0.35,
                min(0.95, 0.30 + 0.15 * len(self.pipeline._session_targets)),
            )

        vitals_n = min(self.vitals_packets, n)
        vitals_csi = csi[-vitals_n:]
        vitals_rssi = rssi[-vitals_n:] if rssi is not None and len(rssi) >= vitals_n else rssi
        t_sec = float(timestamps_ms[-1]) / 1000.0
        return process_hardware_window(
            self.pipeline,
            csi,
            t_sec,
            self.node_id,
            vitals_csi=vitals_csi,
            rssi=rssi,
            area_margin_m=self.area_margin_m,
            max_per_node=self.max_per_node,
            min_confidence=self.min_confidence,
            motion_info=motion_info,
        )

    @property
    def last_motion_score(self) -> float:
        return self._last_motion_score


def fuse_multinode_targets(target_dicts: list[dict], gate_m: float = 1.6) -> list[dict]:
    """Merge duplicate targets from multiple ESP32 nodes (outdoor perimeter array)."""
    if not target_dicts:
        return []

    clusters: list[dict] = []
    for t in target_dicts:
        weight = float(t.get("confidence", 0.5))
        merged = False
        for c in clusters:
            d = (t["x_m"] - c["x_m"]) ** 2 + (t["y_m"] - c["y_m"]) ** 2
            if d < gate_m * gate_m:
                n = c.get("_n", 1.0)
                w_new = n + weight
                c["x_m"] = (c["x_m"] * n + t["x_m"] * weight) / w_new
                c["y_m"] = (c["y_m"] * n + t["y_m"] * weight) / w_new
                c["_n"] = w_new
                c["velocity_mps"] = max(c.get("velocity_mps", 0), t.get("velocity_mps", 0))
                c["respiration_bpm"] = max(c.get("respiration_bpm", 0), t.get("respiration_bpm", 0))
                c["heartbeat_bpm"] = max(c.get("heartbeat_bpm", 0), t.get("heartbeat_bpm", 0))
                c["is_moving"] = c.get("is_moving") or t.get("is_moving")
                c["confidence"] = max(c.get("confidence", 0), t.get("confidence", 0))
                merged = True
                break
        if not merged:
            clusters.append({**t, "_n": weight, "confidence": weight})

    out = []
    for i, c in enumerate(clusters):
        c.pop("_n", None)
        c["id"] = i + 1
        out.append(c)
    return out
