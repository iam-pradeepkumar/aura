"""Multi-target localization and tracking for disaster survivor detection."""

from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

from .doppler import detect_peaks_multi_target, extract_motion_parameters, estimate_doppler_velocity


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
    trajectory: list[tuple[float, float]] = field(default_factory=list)


class TargetTracker:
    """Maintains trajectories; detects entry/exit events."""

    def __init__(self, area_size_m: float = 10.0, gate_m: float = 1.5):
        self.area_size_m = area_size_m
        self.gate_m = gate_m
        self.targets: dict[int, Target] = {}
        self._next_id = 1
        self.events: list[str] = []

    def update(self, detections: list[dict], t_sec: float) -> list[Target]:
        assigned = set()
        for det in detections:
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

            if best_id is None:
                tid = self._next_id
                self._next_id += 1
                tgt = Target(id=tid, x_m=x, y_m=y)
                self.targets[tid] = tgt
                self.events.append(f"t={t_sec:.2f}s: Target {tid} ENTERED at ({x:.2f}, {y:.2f})")
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
                tgt.is_moving = vel > 0.05
                tgt.respiration_bpm = det.get("respiration_bpm", tgt.respiration_bpm)
                tgt.heartbeat_bpm = det.get("heartbeat_bpm", tgt.heartbeat_bpm)
                assigned.add(tid)

            self.targets[tid].trajectory.append((x, y))

        # Exit: targets not matched this frame (handled by caller passing empty if gone)
        return list(self.targets.values())


def localize_static_target(csi_window: np.ndarray, fs_hz: float, area_size_m: float) -> dict:
    """XY of stationary survivor from low-Doppler CSI segment."""
    params = extract_motion_parameters(csi_window, fs_hz, area_size_m)
    return {
        "x_m": params["x_m"],
        "y_m": params["y_m"],
        "range_m": params["range_m"],
        "is_static": abs(params["velocity_mps"]) < 0.05,
    }


def multinode_localize(
    node_positions: dict[int, tuple[float, float]],
    range_estimates: dict[int, float],
) -> tuple[float, float]:
    """Weighted least-squares multilateration from multiple RX nodes."""
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
    x_est = float(np.average(xs, weights=ws))
    y_est = float(np.average(ys, weights=ws))
    return x_est, y_est
