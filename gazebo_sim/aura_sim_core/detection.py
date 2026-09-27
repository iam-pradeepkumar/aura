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


@dataclass
class SimulationDetector:
    """Ramp confidence when a spiderbot is near a victim and slow enough for CSI vitals."""

    world: DisasterWorld
    presence_radius_m: float = 4.5
    confirm_threshold: float = 0.65
    tracks: dict[int, VictimTrack] = field(default_factory=dict)

    def scan(self, node_id: int, x: float, y: float, linear_mps: float, holding: bool, dt: float) -> None:
        slow_enough = linear_mps < 0.18 or holding
        for victim in self.world.victims:
            dist = math.hypot(x - victim.x, y - victim.y)
            track = self.tracks.setdefault(victim.id, VictimTrack(victim.id))
            if dist > self.presence_radius_m:
                track.confidence = max(0.0, track.confidence - dt * 0.04)
                continue
            if not slow_enough:
                track.confidence = max(0.0, track.confidence - dt * 0.02)
                continue
            proximity = 1.0 - dist / self.presence_radius_m
            track.confidence = min(1.0, track.confidence + dt * (0.28 + 0.32 * proximity))
            track.scanning_node = node_id
            if track.confidence >= self.confirm_threshold:
                track.confirmed = True

    def confirmed_ids(self) -> set[int]:
        return {vid for vid, tr in self.tracks.items() if tr.confirmed}

    def targets(self, min_confidence: float = 0.22) -> list[dict]:
        out: list[dict] = []
        victims = {v.id: v for v in self.world.victims}
        for vid, track in self.tracks.items():
            if track.confidence < min_confidence:
                continue
            victim = victims.get(vid)
            if victim is None:
                continue
            conf = track.confidence if track.confirmed else track.confidence * 0.55
            resp_conf = conf * 0.92 if track.confirmed else conf * 0.25
            out.append({
                "id": victim.id,
                "x_m": victim.x,
                "y_m": victim.y,
                "confidence": round(conf, 3),
                "respiration_bpm": victim.resp_bpm,
                "heartbeat_bpm": victim.resp_bpm * 4.2,
                "resp_confidence": round(resp_conf, 3),
                "is_moving": False,
                "suggested_triage": "START" if track.confirmed else "assessing",
                "vitals_quality": round(conf, 3),
            })
        return out
