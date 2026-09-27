"""WebSocket bridge message schema — TITAN command center + aura_processor shape."""

from __future__ import annotations

from typing import Any


def bridge_message_schema() -> dict[str, Any]:
    return {
        "type": "command_sensing",
        "timestamp": "float epoch seconds",
        "mode": "simulation|hardware",
        "mission": {"phase": "patrol|holding|complete", "units": "[]"},
        "zone": {"polygon": "[[x,y],...]", "obstacles": "[]"},
        "data": {"target_count": "int", "targets": "[]"},
    }


def frame_to_bridge_message(
    frame: dict,
    mission_status: dict,
    *,
    mode: str = "simulation",
    zone_polygon: list | None = None,
    obstacles: list | None = None,
    units_roster: list | None = None,
) -> dict:
    targets = []
    for t in frame.get("targets", []):
        conf = float(t.get("confidence", 0))
        resp_conf = float(t.get("resp_confidence", 0))
        targets.append({
            "id": t.get("id"),
            "x_m": t.get("x_m"),
            "y_m": t.get("y_m"),
            "confidence": conf,
            "probability_pct": round(conf * 100, 1),
            "is_moving": t.get("is_moving", False),
            "respiration_bpm": t.get("respiration_bpm", 0),
            "heartbeat_bpm": t.get("heartbeat_bpm", 0),
            "resp_confidence": resp_conf,
            "vitals_confidence_pct": round(resp_conf * 100, 1),
            "suggested_triage": t.get("suggested_triage"),
            "vitals_quality": t.get("vitals_quality", 0),
            "trajectory": t.get("trajectory", []),
        })
    obs_out = []
    if obstacles:
        for o in obstacles:
            if hasattr(o, "x"):
                obs_out.append({"x": o.x, "y": o.y, "radius": o.radius})
            else:
                obs_out.append({"x": o[0], "y": o[1], "radius": o[2]})
    return {
        "type": "command_sensing",
        "timestamp": frame.get("timestamp"),
        "mode": mode,
        "mission": mission_status,
        "zone": {
            "polygon": zone_polygon or [],
            "obstacles": obs_out,
            "area_size_m": frame.get("area_size_m", 40.0),
        },
        "units_roster": units_roster or mission_status.get("units", []),
        "data": {
            "target_count": frame.get("target_count", 0),
            "motion_detected": frame.get("motion_detected", False),
            "sensing_confidence": frame.get("sensing_confidence", 0),
            "respiration_bpm": frame.get("respiration_bpm", 0),
            "heartbeat_bpm": frame.get("heartbeat_bpm", 0),
            "respiration_waveform": frame.get("respiration_waveform", []),
            "heartbeat_waveform": frame.get("heartbeat_waveform", []),
            "targets": targets,
            "confidence": frame.get("sensing_confidence", 0),
            "survivors_detected": frame.get("target_count", 0),
        },
        "node_positions": frame.get("node_positions", {}),
        "area_size_m": frame.get("area_size_m", 40.0),
        "processor_version": frame.get("processor_version"),
        "events": frame.get("events", []),
        "distress_events": frame.get("distress_events", []),
    }
