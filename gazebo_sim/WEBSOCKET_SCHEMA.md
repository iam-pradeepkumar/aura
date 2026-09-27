# Mobile SAR WebSocket Bridge Schema

**Endpoint:** `WS /ws/command` (TITAN dashboard) · legacy `WS /ws/mobile` · standalone `ws://127.0.0.1:8766`

**Direction:** Server → client push (~5 Hz)

## Message envelope

```json
{
  "type": "mobile_sensing",
  "timestamp": 1730000000.0,
  "mode": "mobile",
  "processor_version": "2026.09.26-v2",
  "area_size_m": 40.0,
  "node_positions": {
    "1": [12.4, 8.1],
    "2": [20.0, 15.0]
  },
  "mission": {
    "phase": "patrol",
    "elapsed_sec": 42.5,
    "coverage_pct": 18.3,
    "confirmed_detections": 1,
    "rover": { "x": 12.4, "y": 8.1, "holding": true, "finished": false },
    "drone": { "x": 20.0, "y": 15.0, "z": 6.0, "waypoint_idx": 3, "finished": false }
  },
  "data": {
    "target_count": 1,
    "motion_detected": true,
    "sensing_confidence": 0.62,
    "confidence": 0.62,
    "respiration_bpm": 14.0,
    "heartbeat_bpm": 0.0,
    "respiration_waveform": [],
    "heartbeat_waveform": [],
    "targets": [
      {
        "id": 1,
        "x_m": 16.2,
        "y_m": 9.4,
        "confidence": 0.58,
        "is_moving": false,
        "respiration_bpm": 14.0,
        "resp_confidence": 0.55,
        "suggested_triage": "delayed",
        "vitals_quality": 0.48
      }
    ]
  },
  "events": [],
  "distress_events": []
}
```

## Field compatibility

The `data` object is shaped to match `dashboard.js` `updateSensingUI()` and WiMANS `result_to_dict()`:

| Field | Type | Notes |
|-------|------|-------|
| `data.target_count` | int | Matches map marker count policy |
| `data.motion_detected` | bool | Coarse presence while rover moving |
| `data.respiration_bpm` | float | Only non-zero after 3 s stationary + hold |
| `data.targets[].x_m`, `y_m` | float | Fused survivor position (m) |
| `data.targets[].resp_confidence` | float | 0–1, from `sensing_v2` ensemble |
| `node_positions` | dict | **Runtime** mobile node XY (not static corners) |

## Client → server

Dashboard: `POST /api/mobile/start` — no body required.

Standalone bridge: connect only; mission auto-starts on server boot.
