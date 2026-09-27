"""Simulation-only survivor detection — CSI-gated proximity model for dashboard missions."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .world import DisasterWorld, Victim


@dataclass
class VictimTrack:
    victim_id: int
    confidence: float = 0.0
    confirmed: bool = False
    scanning_node: int | None = None
    locked_x: float | None = None
    locked_y: float | None = None


@dataclass
class SimulationDetector:
    """Ramp confidence when a spiderbot is near a victim and slow enough for CSI vitals."""

    world: DisasterWorld
    presence_radius_m: float = 4.5
    confirm_threshold: float = 0.65
    tracks: dict[int, VictimTrack] = field(default_factory=dict)

    def scan(self, node_id: int, x: float, y: float, linear_mps: float, holding: bool, dt: float) -> None:
        for victim in self.world.victims:
            dist = math.hypot(x - victim.x, y - victim.y)
            track = self.tracks.setdefault(victim.id, VictimTrack(victim.id))
            if dist > self.presence_radius_m:
                track.confidence = max(0.0, track.confidence - dt * 0.04)
                continue
            slow_enough = holding or dist < self.presence_radius_m * 0.75 or linear_mps < 0.35
            if not slow_enough:
                track.confidence = max(0.0, track.confidence - dt * 0.02)
                continue
            proximity = 1.0 - dist / self.presence_radius_m
            track.confidence = min(1.0, track.confidence + dt * (0.35 + 0.45 * proximity))
            track.scanning_node = node_id
            if track.confidence >= self.confirm_threshold:
                track.confirmed = True
                track.locked_x = victim.x
                track.locked_y = victim.y

    def confirmed_ids(self) -> set[int]:
        return {vid for vid, tr in self.tracks.items() if tr.confirmed}

    def targets(self, min_confidence: float = 0.18) -> list[dict]:
        out: list[dict] = []
        victims = {v.id: v for v in self.world.victims}
        for vid, track in self.tracks.items():
            victim = victims.get(vid)
            if victim is None:
                continue
            if not track.confirmed and track.confidence < min_confidence:
                continue
            x = track.locked_x if track.locked_x is not None else victim.x
            y = track.locked_y if track.locked_y is not None else victim.y
            conf = max(track.confidence, 0.72) if track.confirmed else track.confidence * 0.6
            resp_conf = 0.92 if track.confirmed else conf * 0.3
            out.append({
                "id": victim.id,
                "x_m": x,
                "y_m": y,
                "confidence": round(conf, 3),
                "confirmed": track.confirmed,
                "respiration_bpm": victim.resp_bpm,
                "heartbeat_bpm": victim.resp_bpm * 4.2,
                "resp_confidence": round(resp_conf, 3),
                "is_moving": False,
                "suggested_triage": "START" if track.confirmed else "assessing",
                "vitals_quality": round(conf, 3),
            })
        return out
