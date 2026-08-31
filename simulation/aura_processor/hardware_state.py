"""Persistent CSI buffers and pipelines for live ESP32 hardware."""

from __future__ import annotations

import numpy as np

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
    ):
        self.node_id = node_id
        self.pipeline = pipeline
        self.min_packets = min_packets
        self.refresh_every = refresh_every
        self.motion_threshold_scale = motion_threshold_scale
        self._packet_count = 0
        self._sensor_xy = pipeline.node_positions.get(node_id, pipeline.sensor_xy)

    def process(self, csi: np.ndarray, timestamps_ms: np.ndarray):
        n = len(csi)
        if n < self.min_packets:
            return None

        fs = estimate_fs_hz(timestamps_ms)
        self.pipeline.fs_hz = fs
        # Longer window outdoors (~10 s at 20 Hz) for stable vitals
        self.pipeline.window_samples = max(self.min_packets, min(int(2.5 * fs), n))

        self._packet_count += 1
        if self._packet_count == 1 or self._packet_count % self.refresh_every == 0:
            eff_threshold = self.pipeline.motion_threshold * self.motion_threshold_scale
            self.pipeline._session_targets = detect_hardware_session_targets(
                csi,
                fs,
                self.pipeline.area_size_m,
                self.pipeline.max_targets,
                self._sensor_xy,
                motion_threshold=eff_threshold,
            )
            self.pipeline.estimated_person_count = len(self.pipeline._session_targets)
            self.pipeline.session_confidence = max(
                0.35,
                min(0.95, 0.25 + 0.12 * len(self.pipeline._session_targets)),
            )

        t_sec = float(timestamps_ms[-1]) / 1000.0
        return process_hardware_window(self.pipeline, csi, t_sec, self.node_id)


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
