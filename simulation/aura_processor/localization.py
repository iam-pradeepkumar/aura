"""Multi-target localization and tracking for disaster survivor detection."""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np


@dataclass
class Target:
    id: int
    x_m: float
    y_m: float
    velocity_mps: float = 0.0
    acceleration_mps2: float = 0.0
    is_moving: bool = True
    respiration_bpm: float = 0.0
    heartbeat_bpm: float = 0.0
    respiration_waveform: np.ndarray | None = None
    heartbeat_waveform: np.ndarray | None = None
    trajectory: list[tuple[float, float]] = field(default_factory=list)


class TargetTracker:
    """Maintains trajectories; detects entry/exit events."""

    def __init__(self, area_size_m: float = 10.0, gate_m: float = 2.5, max_targets: int = 6):
        self.area_size_m = area_size_m
        self.gate_m = gate_m
        self.max_targets = max_targets
        self.targets: dict[int, Target] = {}
        self._next_id = 1
        self.events: list[str] = []

    def reset(self) -> None:
        self.targets.clear()
        self._next_id = 1
        self.events.clear()

    def update(self, detections: list[dict], t_sec: float) -> list[Target]:
        # Cap detections to max_targets by weight/velocity
        dets = sorted(detections, key=lambda d: d.get("weight", 1.0), reverse=True)[: self.max_targets]

        assigned = set()
        matched_ids = set()

        for det in dets:
            x, y = det["x_m"], det["y_m"]
            best_id = None
            best_dist = self.gate_m
            for tid, tgt in self.targets.items():
                if tid in assigned:
                    continue
                d = np.hypot(x - tgt.x_m, y - tgt.y_m)
                if d < best_dist:
                    best_dist = d
                    best_id = tid

            if best_id is None and len(self.targets) >= self.max_targets:
                continue

            if best_id is None:
                tid = self._next_id
                self._next_id += 1
                tgt = Target(id=tid, x_m=x, y_m=y)
                self.targets[tid] = tgt
                self.events.append(f"t={t_sec:.2f}s: Target {tid} at ({x:.1f}, {y:.1f})")
            else:
                tid = best_id
                tgt = self.targets[tid]
                dt = max(det.get("dt", 0.05), 1e-3)
                vx = (x - tgt.x_m) / dt
                vy = (y - tgt.y_m) / dt
                vel = float(np.hypot(vx, vy))
                acc = (vel - tgt.velocity_mps) / dt
                tgt.acceleration_mps2 = acc
                tgt.velocity_mps = vel
                tgt.x_m, tgt.y_m = x, y
                tgt.is_moving = vel > 0.08 or det.get("velocity_mps", 0) > 0.08
                tgt.respiration_bpm = det.get("respiration_bpm", tgt.respiration_bpm)
                tgt.heartbeat_bpm = det.get("heartbeat_bpm", tgt.heartbeat_bpm)
                if det.get("respiration_waveform") is not None:
                    tgt.respiration_waveform = det["respiration_waveform"]
                if det.get("heartbeat_waveform") is not None:
                    tgt.heartbeat_waveform = det["heartbeat_waveform"]
                assigned.add(tid)
                matched_ids.add(tid)

            self.targets[tid].trajectory.append((x, y))
            if len(self.targets[tid].trajectory) > 40:
                self.targets[tid].trajectory = self.targets[tid].trajectory[-40:]

        return list(self.targets.values())


def multinode_localize(
    node_positions: dict[int, tuple[float, float]],
    range_estimates: dict[int, float],
) -> tuple[float, float]:
    if not range_estimates:
        return 0.0, 0.0
    xs, ys, ws = [], [], []
    for nid, rng in range_estimates.items():
        if nid not in node_positions:
            continue
        nx, ny = node_positions[nid]
        xs.append(nx)
        ys.append(ny)
        ws.append(1.0 / max(rng, 0.5) ** 2)
    if not xs:
        return 0.0, 0.0
    xs, ys, ws = np.array(xs), np.array(ys), np.array(ws)
    return float(np.average(xs, weights=ws)), float(np.average(ys, weights=ws))
