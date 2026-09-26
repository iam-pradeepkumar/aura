"""Shared data types for AURA sensing_v2.

Informed by techniques described in wifi-densepose-mat ADR-001,
reimplemented for ESP32 CSI in AURA.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VitalsEstimate:
    resp_bpm: float = 0.0
    hr_bpm: float = 0.0
    resp_confidence: float = 0.0
    hr_confidence: float = 0.0
    quality: float = 0.0
    respiration_waveform: Any = None
    heartbeat_waveform: Any = None


@dataclass
class DistressEvent:
    type: str  # fall | collapse | irregular_breathing
    timestamp: float
    target_id: int = 0
    confidence: float = 0.0


@dataclass
class SurvivorObservation:
    x_m: float
    y_m: float
    velocity_mps: float = 0.0
    confidence: float = 0.0
    is_moving: bool = False
    source_node: int = 0
    resp_bpm: float = 0.0
    hr_bpm: float = 0.0
    resp_confidence: float = 0.0
    hr_confidence: float = 0.0
    vitals_quality: float = 0.0
    respiration_waveform: Any = None
    heartbeat_waveform: Any = None
    distress_events: list[DistressEvent] = field(default_factory=list)
    suggested_triage: str | None = None
    triage_confidence: float = 0.0
    depth_band: str | None = None

    def to_detection_dict(self) -> dict:
        """Convert to legacy detection dict for fusion/tracker."""
        return {
            "x_m": self.x_m,
            "y_m": self.y_m,
            "velocity_mps": self.velocity_mps,
            "confidence": self.confidence,
            "is_moving": self.is_moving,
            "source_node": self.source_node,
            "respiration_bpm": self.resp_bpm,
            "heartbeat_bpm": self.hr_bpm,
            "resp_confidence": self.resp_confidence,
            "hr_confidence": self.hr_confidence,
            "vitals_quality": self.vitals_quality,
            "respiration_waveform": self.respiration_waveform,
            "heartbeat_waveform": self.heartbeat_waveform,
            "distress_events": [e.__dict__ for e in self.distress_events],
            "suggested_triage": self.suggested_triage,
            "triage_confidence": self.triage_confidence,
            "depth_band": self.depth_band,
        }
