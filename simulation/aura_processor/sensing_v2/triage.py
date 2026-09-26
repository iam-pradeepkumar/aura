"""START-protocol triage suggestions for sensing_v2.

Informed by techniques described in wifi-densepose-mat ADR-001 (TriageCalculator),
reimplemented for ESP32 CSI in AURA. Output is suggestion only — human must approve.
"""

from __future__ import annotations

from .types import DistressEvent


TRIAGE_IMMEDIATE = "immediate"
TRIAGE_DELAYED = "delayed"
TRIAGE_MINOR = "minor"
TRIAGE_NONE = None


def suggest_triage(
    *,
    resp_bpm: float,
    resp_confidence: float,
    velocity_mps: float,
    is_moving: bool,
    presence_confidence: float,
    distress_events: list[DistressEvent] | list[dict],
    fall_window_sec: float = 60.0,
    t_sec: float = 0.0,
) -> tuple[str | None, float]:
    """Map CSI observations to START-style suggested triage."""
    if presence_confidence < 0.3:
        return TRIAGE_NONE, 0.0

    fall_recent = False
    for e in distress_events:
        etype = e.type if hasattr(e, "type") else e.get("type", "")
        ts = e.timestamp if hasattr(e, "timestamp") else e.get("timestamp", 0)
        if etype in ("fall", "collapse") and (t_sec - float(ts)) <= fall_window_sec:
            fall_recent = True
            break

    # Immediate (Red): abnormal resp or fall + low movement after
    abnormal_resp = resp_bpm > 0 and (resp_bpm < 10 or resp_bpm > 29)
    irregular = any(
        (e.type if hasattr(e, "type") else e.get("type")) == "irregular_breathing"
        for e in distress_events
    )

    if fall_recent and not is_moving:
        return TRIAGE_IMMEDIATE, float(min(0.55 + presence_confidence * 0.3, 0.85))

    if (abnormal_resp or irregular) and resp_confidence >= 0.35:
        conf = float(min(0.45 + resp_confidence * 0.4, 0.8))
        return TRIAGE_IMMEDIATE, conf

    # Delayed (Yellow): stable resp, low movement
    if (
        8 <= resp_bpm <= 20
        and resp_confidence >= 0.4
        and velocity_mps < 0.25
        and presence_confidence >= 0.5
    ):
        return TRIAGE_DELAYED, float(min(0.5 + resp_confidence * 0.35, 0.75))

    # Minor (Green): walking signature
    if velocity_mps > 0.3 and is_moving:
        return TRIAGE_MINOR, float(min(0.4 + presence_confidence * 0.3, 0.65))

    return TRIAGE_NONE, 0.0


def triage_label(triage: str | None) -> str:
    return {
        TRIAGE_IMMEDIATE: "IMMEDIATE (Red)",
        TRIAGE_DELAYED: "DELAYED (Yellow)",
        TRIAGE_MINOR: "MINOR (Green)",
    }.get(triage or "", "—")
