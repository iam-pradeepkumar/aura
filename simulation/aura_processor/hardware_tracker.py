"""Global multi-target tracker for live hardware — low-latency motion trails."""

from __future__ import annotations

import time

import numpy as np


class FieldTracker:
    """Fuse per-frame detections into stable IDs with responsive position updates."""

    def __init__(
        self,
        area_size_m: float = 10.0,
        gate_m: float = 2.2,
        max_targets: int = 8,
        trail_len: int = 40,
        motion_threshold_mps: float = 0.08,
        position_alpha: float = 0.78,
        max_miss_frames: int = 6,
    ):
        self.area_size_m = area_size_m
        self.gate_m = gate_m
        self.max_targets = max_targets
        self.trail_len = trail_len
        self.motion_threshold_mps = motion_threshold_mps
        self.position_alpha = position_alpha
        self.max_miss_frames = max_miss_frames
        self._targets: dict[int, dict] = {}
        self._next_id = 1
        self.events: list[str] = []
        self._last_t: float | None = None

    def reset(self) -> None:
        self._targets.clear()
        self._next_id = 1
        self.events.clear()
        self._last_t = None

    def update(self, detections: list[dict], t_sec: float | None = None) -> list[dict]:
        now = float(t_sec if t_sec is not None else time.time())
        dt = 0.15 if self._last_t is None else max(now - self._last_t, 0.05)
        self._last_t = now

        dets = sorted(
            detections,
            key=lambda d: (d.get("confidence", 0), d.get("velocity_mps", 0)),
            reverse=True,
        )[: self.max_targets]

        assigned: set[int] = set()
        matched: set[int] = set()

        for det in dets:
            x = float(det["x_m"])
            y = float(det["y_m"])
            best_id = None
            best_dist = self.gate_m

            for tid, tgt in self._targets.items():
                if tid in assigned:
                    continue
                d = float(np.hypot(x - tgt["x_m"], y - tgt["y_m"]))
                if d < best_dist:
                    best_dist = d
                    best_id = tid

            if best_id is None and len(self._targets) >= self.max_targets:
                continue

            alpha = self.position_alpha
            if best_id is None:
                tid = self._next_id
                self._next_id += 1
                was_moving = False
                self._targets[tid] = {
                    "id": tid,
                    "x_m": x,
                    "y_m": y,
                    "velocity_mps": float(det.get("velocity_mps", 0)),
                    "acceleration_mps2": 0.0,
                    "is_moving": bool(det.get("is_moving")),
                    "respiration_bpm": det.get("respiration_bpm", 0.0),
                    "heartbeat_bpm": det.get("heartbeat_bpm", 0.0),
                    "respiration_waveform": det.get("respiration_waveform", []),
                    "heartbeat_waveform": det.get("heartbeat_waveform", []),
                    "confidence": det.get("confidence", 0.0),
                    "trajectory": [(x, y)],
                }
                self.events.append(f"t={now:.1f}s: Target {tid} at ({x:.1f}, {y:.1f})")
                assigned.add(tid)
                matched.add(tid)
            else:
                tid = best_id
                tgt = self._targets[tid]
                was_moving = tgt.get("is_moving", False)
                px, py = tgt["x_m"], tgt["y_m"]
                sx = alpha * x + (1.0 - alpha) * px
                sy = alpha * y + (1.0 - alpha) * py
                vx = (sx - px) / dt
                vy = (sy - py) / dt
                vel = float(np.hypot(vx, vy))
                vel = max(vel, float(det.get("velocity_mps", 0)))
                tgt["x_m"] = sx
                tgt["y_m"] = sy
                tgt["velocity_mps"] = vel
                tgt["acceleration_mps2"] = (vel - tgt.get("velocity_mps", 0.0)) / dt
                tgt["is_moving"] = vel > self.motion_threshold_mps or bool(det.get("is_moving"))
                tgt["respiration_bpm"] = max(tgt.get("respiration_bpm", 0), det.get("respiration_bpm", 0))
                tgt["heartbeat_bpm"] = max(tgt.get("heartbeat_bpm", 0), det.get("heartbeat_bpm", 0))
                if det.get("respiration_waveform"):
                    tgt["respiration_waveform"] = det["respiration_waveform"]
                if det.get("heartbeat_waveform"):
                    tgt["heartbeat_waveform"] = det["heartbeat_waveform"]
                tgt["confidence"] = max(tgt.get("confidence", 0), det.get("confidence", 0))
                traj = list(tgt.get("trajectory", []))
                traj.append((sx, sy))
                tgt["trajectory"] = traj[-self.trail_len :]
                assigned.add(tid)
                matched.add(tid)

                if tgt["is_moving"] and not was_moving:
                    self.events.append(f"t={now:.1f}s: Target {tid} moving")
                elif not tgt["is_moving"] and was_moving:
                    self.events.append(f"t={now:.1f}s: Target {tid} stopped")

        for tid in list(self._targets):
            if tid in matched:
                self._targets[tid]["_miss"] = 0
            else:
                miss = int(self._targets[tid].get("_miss", 0)) + 1
                self._targets[tid]["_miss"] = miss
                if miss > self.max_miss_frames:
                    self.events.append(f"t={now:.1f}s: Target {tid} lost")
                    del self._targets[tid]

        if len(self.events) > 30:
            self.events = self.events[-30:]

        out = []
        for tid in sorted(self._targets):
            t = dict(self._targets[tid])
            t.pop("_last_seen", None)
            t.pop("_miss", None)
            t["trajectory"] = [(round(a, 3), round(b, 3)) for a, b in t.get("trajectory", [])]
            t["x_m"] = round(t["x_m"], 3)
            t["y_m"] = round(t["y_m"], 3)
            t["velocity_mps"] = round(t.get("velocity_mps", 0), 3)
            out.append(t)
        return out
