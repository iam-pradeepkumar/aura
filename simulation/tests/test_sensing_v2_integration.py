"""Integration tests for sensing_v2 engine wiring."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "simulation"))

from aura_processor.hardware_fusion import fuse_hardware_targets  # noqa: E402
from aura_processor.hardware_live import load_field_config, LiveFieldEngine  # noqa: E402
from aura_processor.hardware_tracker import FieldTracker  # noqa: E402
from aura_processor.sensing_v2.enricher import SensingV2Enricher  # noqa: E402


def test_config_sensing_engine_v2() -> None:
    cfg = load_field_config(str(ROOT / "simulation" / "config.yaml"))
    assert cfg.get("hardware", {}).get("sensing_engine") == "v2"


def test_fusion_preserves_v2_fields() -> None:
    targets = [
        {
            "x_m": 4.9,
            "y_m": 5.1,
            "confidence": 0.55,
            "source_node": 1,
            "resp_confidence": 0.62,
            "hr_confidence": 0.2,
            "vitals_quality": 0.7,
            "depth_band": "surface",
        },
        {
            "x_m": 5.0,
            "y_m": 4.95,
            "confidence": 0.52,
            "source_node": 2,
            "resp_confidence": 0.58,
            "hr_confidence": 0.15,
            "vitals_quality": 0.65,
        },
    ]
    fused = fuse_hardware_targets(
        targets,
        area_size_m=10.0,
        gate_m=3.0,
        min_node_votes=2,
        min_confidence=0.34,
        motion_active_nodes=2,
    )
    assert len(fused) == 1
    assert fused[0]["resp_confidence"] >= 0.58
    assert fused[0]["vitals_quality"] >= 0.65
    assert fused[0]["depth_band"] == "surface"


def test_tracker_kalman_spawn() -> None:
    tr = FieldTracker(use_kalman=True, min_spawn_confidence=0.4)
    out = tr.update([{"x_m": 3.0, "y_m": 4.0, "confidence": 0.6, "velocity_mps": 0.1}])
    assert len(out) == 1
    out2 = tr.update([{"x_m": 3.2, "y_m": 4.1, "confidence": 0.6, "velocity_mps": 0.15}])
    assert len(out2) == 1
    assert out2[0]["id"] == out[0]["id"]


def test_enricher_triage_on_targets() -> None:
    cfg = {
        "hardware": {
            "sensing_v2": {"fall_detection": True, "triage_suggestions": True},
            "dm_bridge": {"enabled": False},
            "mqtt": {"enabled": False},
        }
    }
    enricher = SensingV2Enricher(cfg)
    targets = [
        {
            "id": 1,
            "x_m": 5.0,
            "y_m": 5.0,
            "velocity_mps": 0.05,
            "is_moving": False,
            "confidence": 0.65,
            "respiration_bpm": 14.0,
            "resp_confidence": 0.55,
        }
    ]
    enriched, events = enricher.enrich_targets(targets, motion_score=0.4, baseline=0.3, t_sec=100.0)
    assert enriched[0].get("suggested_triage") == "delayed"
    assert isinstance(events, list)


def test_live_engine_v2_initialization() -> None:
    cfg = load_field_config(str(ROOT / "simulation" / "config.yaml"))
    engine = LiveFieldEngine(cfg, port=15555)
    assert engine._sensing_engine == "v2"
    assert engine._v2_enricher is not None
    assert engine.tracker.use_kalman is True
