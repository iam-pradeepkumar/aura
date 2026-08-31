"""Persistent CSI buffers and pipelines for live ESP32 hardware."""

from __future__ import annotations

import numpy as np

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
    """Per-node CSI accumulation + session-level target tracking."""

    def __init__(
        self,
        node_id: int,
        pipeline: AURAPipeline,
        min_packets: int = 64,
        refresh_every: int = 32,
    ):
        self.node_id = node_id
        self.pipeline = pipeline
        self.min_packets = min_packets
        self.refresh_every = refresh_every
        self._packet_count = 0

    def process(self, csi: np.ndarray, timestamps_ms: np.ndarray):
        from .pipeline import SensingResult

        n = len(csi)
        if n < self.min_packets:
            return None

        fs = estimate_fs_hz(timestamps_ms)
        self.pipeline.fs_hz = fs
        self.pipeline.window_samples = max(self.min_packets, min(int(2.0 * fs), n))

        self._packet_count += 1
        if self._packet_count == 1 or self._packet_count % self.refresh_every == 0:
            self.pipeline.set_session_targets(
                csi,
                sensor_xy=self.pipeline.node_positions.get(self.node_id, self.pipeline.sensor_xy),
            )

        t_sec = float(timestamps_ms[-1]) / 1000.0
        return self.pipeline.process_window(csi, t_sec, node_id=self.node_id)


def fuse_multinode_targets(target_dicts: list[dict], gate_m: float = 1.8) -> list[dict]:
    """Merge duplicate targets reported by multiple ESP32 nodes."""
    if not target_dicts:
        return []

    clusters: list[dict] = []
    for t in target_dicts:
        merged = False
        for c in clusters:
            d = (t["x_m"] - c["x_m"]) ** 2 + (t["y_m"] - c["y_m"]) ** 2
            if d < gate_m * gate_m:
                n = c.get("_n", 1) + 1
                c["x_m"] = (c["x_m"] * c.get("_n", 1) + t["x_m"]) / n
                c["y_m"] = (c["y_m"] * c.get("_n", 1) + t["y_m"]) / n
                c["_n"] = n
                c["velocity_mps"] = max(c.get("velocity_mps", 0), t.get("velocity_mps", 0))
                c["respiration_bpm"] = max(c.get("respiration_bpm", 0), t.get("respiration_bpm", 0))
                c["heartbeat_bpm"] = max(c.get("heartbeat_bpm", 0), t.get("heartbeat_bpm", 0))
                c["is_moving"] = c.get("is_moving") or t.get("is_moving")
                merged = True
                break
        if not merged:
            clusters.append({**t, "_n": 1})

    out = []
    for i, c in enumerate(clusters):
        c.pop("_n", None)
        c["id"] = i + 1
        out.append(c)
    return out
