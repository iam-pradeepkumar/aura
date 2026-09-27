"""WebSocket bridge message schema — matches dashboard + aura_processor frame shape."""

from __future__ import annotations

from typing import Any


def bridge_message_schema() -> dict[str, Any]:
    return {
        "type": "mobile_sensing",
        "timestamp": "float epoch seconds",
        "mission": {
            "phase": "patrol|holding|complete",
            "elapsed_sec": "float",
            "coverage_pct": "float 0-100",
            "confirmed_detections": "int",
            "rover": {"x": "float", "y": "float", "holding": "bool"},
            "drone": {"x": "float", "y": "float", "z": "float", "waypoint_idx": "int"},
        },
        "data": {
            "target_count": "int",
            "motion_detected": "bool",
            "sensing_confidence": "float",
            "respiration_bpm": "float",
            "heartbeat_bpm": "float",
            "targets": [
                {
                    "id": "int",
                    "x_m": "float",
                    "y_m": "float",
                    "confidence": "float",
                    "is_moving": "bool",
                    "respiration_bpm": "float",
                    "resp_confidence": "float",
                    "suggested_triage": "immediate|delayed|minor|null",
                }
            ],
        },
        "node_positions": {"node_id": "[x_m, y_m]"},
        "area_size_m": "float",
        "processor_version": "string",
        "mode": "mobile",
    }


def frame_to_bridge_message(frame: dict, mission_status: dict) -> dict:
    """Convert MobileFieldEngine frame + mission metadata to WS payload."""
    targets = []
    for t in frame.get("targets", []):
        targets.append({
            "id": t.get("id"),
            "x_m": t.get("x_m"),
            "y_m": t.get("y_m"),
            "confidence": t.get("confidence", 0),
            "is_moving": t.get("is_moving", False),
            "respiration_bpm": t.get("respiration_bpm", 0),
            "resp_confidence": t.get("resp_confidence", 0),
            "suggested_triage": t.get("suggested_triage"),
            "vitals_quality": t.get("vitals_quality", 0),
        })
    return {
        "type": "mobile_sensing",
        "timestamp": frame.get("timestamp"),
        "mission": mission_status,
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
        },
        "node_positions": frame.get("node_positions", {}),
        "area_size_m": frame.get("area_size_m", 40.0),
        "processor_version": frame.get("processor_version"),
        "mode": "mobile",
        "events": frame.get("events", []),
        "distress_events": frame.get("distress_events", []),
    }
