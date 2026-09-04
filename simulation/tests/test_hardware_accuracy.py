"""Accuracy regression tests for live ESP32 multinode sensing pipeline."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "simulation"))

from aura_processor.hardware_accuracy import (  # noqa: E402
    SceneCalibrator,
    estimate_sensing_confidence,
    multinode_motion_verdict,
    select_best_vitals,
)
from aura_processor.hardware_confirm import OccupancyConfirmFilter  # noqa: E402
from aura_processor.hardware_fusion import (  # noqa: E402
    consensus_target_count,
    fuse_hardware_targets,
    fuse_motion_consensus,
)


def _calibrate_empty(cal: SceneCalibrator, noise: float = 0.22, frames: int | None = None) -> None:
    n = frames or cal.frames
    for _ in range(n):
        for nid in cal.expected_ids:
            cal.update(nid, noise + np.random.uniform(-0.04, 0.04))


def test_empty_area_no_motion() -> None:
  """After calibration, low scores on all nodes → no motion."""
  cal = SceneCalibrator(frames=10, expected_ids=[1, 2, 3, 4])
  _calibrate_empty(cal, 0.20)
  assert cal.ready

  scores = {1: 0.21, 2: 0.19, 3: 0.23, 4: 0.20}
  v = multinode_motion_verdict(scores, 0.50, min_nodes=2, calibrator=cal)
  assert not v["motion"]
  assert cal.is_empty_scene(scores, 0.50)


def test_walker_two_nodes_motion() -> None:
  """Two+ nodes above threshold → motion detected."""
  scores = {1: 0.68, 2: 0.64, 3: 0.55, 4: 0.52}
  v = multinode_motion_verdict(scores, 0.50, min_nodes=2)
  assert v["motion"]
  assert v["active_nodes"] >= 2
  assert v["confidence"] >= 0.5


def test_motion_consensus_when_no_xy() -> None:
  """Motion consensus creates a target when localization fails."""
  node_pos = {1: (0.0, 0.0), 2: (10.0, 0.0), 3: (10.0, 10.0), 4: (0.0, 10.0)}
  scores = {1: 0.72, 2: 0.66, 3: 0.48, 4: 0.44}
  fused = fuse_motion_consensus(scores, node_pos, 10.0, motion_min=0.50, min_nodes=2)
  assert len(fused) == 1
  assert fused[0]["node_votes"] >= 2
  assert 0.5 <= fused[0]["x_m"] <= 9.5


def test_fusion_multinode_agreement() -> None:
  """Two nodes localizing nearby → single fused target."""
  targets = [
      {"x_m": 4.8, "y_m": 5.2, "confidence": 0.55, "source_node": 1, "velocity_mps": 0.2},
      {"x_m": 5.1, "y_m": 4.9, "confidence": 0.52, "source_node": 2, "velocity_mps": 0.18},
  ]
  fused = fuse_hardware_targets(
      targets, area_size_m=10.0, gate_m=3.2, min_node_votes=2, min_confidence=0.36,
      motion_active_nodes=2,
  )
  assert len(fused) == 1
  assert fused[0]["node_votes"] >= 2


def test_occupancy_confirms_real_walker() -> None:
  """Temporal filter confirms persistent detections, rejects single-frame noise."""
  occ = OccupancyConfirmFilter(confirm_frames=3, min_node_votes=2, min_confidence=0.36)
  target = {
      "x_m": 5.0, "y_m": 5.0, "confidence": 0.55, "node_votes": 2, "velocity_mps": 0.2,
  }
  assert occ.apply([target]) == []
  assert occ.apply([target]) == []
  confirmed = occ.apply([target])
  assert len(confirmed) == 1

  # Single-frame phantom should not confirm
  occ2 = OccupancyConfirmFilter(confirm_frames=3, min_node_votes=2, min_confidence=0.36)
  weak = {"x_m": 5.0, "y_m": 5.0, "confidence": 0.30, "node_votes": 1}
  for _ in range(5):
      assert occ2.apply([weak]) == []


def test_fast_confirm_high_confidence() -> None:
  """Strong multinode detection confirms in 2 frames."""
  occ = OccupancyConfirmFilter(confirm_frames=3, min_node_votes=2, min_confidence=0.36)
  strong = {
      "x_m": 5.0, "y_m": 5.0, "confidence": 0.62, "node_votes": 3, "velocity_mps": 0.25,
  }
  assert occ.apply([strong]) == []
  confirmed = occ.apply([strong])
  assert len(confirmed) == 1


def test_vitals_selection() -> None:
  """Best vitals picked from static high-SNR node."""
  pool = [
      {"node_id": 1, "respiration_bpm": 12, "heartbeat_bpm": 40, "vitals_snr": 1.0,
       "motion_score": 0.6, "velocity_mps": 0.3},
      {"node_id": 2, "respiration_bpm": 16, "heartbeat_bpm": 72, "vitals_snr": 3.5,
       "motion_score": 0.5, "velocity_mps": 0.05},
  ]
  best = select_best_vitals(pool)
  assert best["source_node"] == 2
  assert best["respiration_bpm"] == 16
  assert best["heartbeat_bpm"] == 72


def test_sensing_confidence_scales() -> None:
  motion_v = {"confidence": 0.8}
  fused = [{"node_votes": 3, "confidence": 0.6}]
  conf = estimate_sensing_confidence(1, motion_v, fused, calibrator_ready=True)
  assert conf >= 0.5

  empty_conf = estimate_sensing_confidence(0, {"confidence": 0.3}, [], True)
  assert empty_conf < 0.15


def test_accuracy_scenarios() -> None:
  """
  Simulated field scenarios — target >90% correct decisions.
  Empty: no motion/count. Occupied: motion + count >= 1.
  """
  cal = SceneCalibrator(frames=8, expected_ids=[1, 2, 3, 4])
  rng = np.random.default_rng(42)

  scenarios: list[tuple[str, dict[int, float], bool]] = []
  # Empty area (20 trials)
  for i in range(20):
      scores = {nid: 0.18 + rng.uniform(0, 0.12) for nid in [1, 2, 3, 4]}
      scenarios.append((f"empty_{i}", scores, False))
  # Single walker (25 trials)
  for i in range(25):
      base = 0.55 + rng.uniform(0, 0.25)
      scores = {
          1: base + rng.uniform(0, 0.15),
          2: base + rng.uniform(0, 0.12),
          3: 0.35 + rng.uniform(0, 0.15),
          4: 0.32 + rng.uniform(0, 0.12),
      }
      scenarios.append((f"walker_{i}", scores, True))
  # Edge: one strong node only (should NOT detect — need 2 nodes)
  for i in range(10):
      scores = {1: 0.75, 2: 0.22, 3: 0.20, 4: 0.19}
      scenarios.append((f"single_node_{i}", scores, False))

  _calibrate_empty(cal, 0.20, frames=8)
  correct = 0
  for _name, scores, expect_motion in scenarios:
      v = multinode_motion_verdict(scores, 0.50, min_nodes=2, calibrator=cal)
      got = bool(v["motion"])
      if got == expect_motion:
          correct += 1

  accuracy = correct / len(scenarios)
  assert accuracy >= 0.90, f"Motion accuracy {accuracy:.1%} below 90% ({correct}/{len(scenarios)})"


def test_consensus_count() -> None:
  assert consensus_target_count([1, 1, 0, 1], 1, 4, motion_active_nodes=2) == 1
  assert consensus_target_count([], 0, 4) == 0
  assert consensus_target_count([2, 2], 2, 4) == 2


if __name__ == "__main__":
  tests = [
      test_empty_area_no_motion,
      test_walker_two_nodes_motion,
      test_motion_consensus_when_no_xy,
      test_fusion_multinode_agreement,
      test_occupancy_confirms_real_walker,
      test_fast_confirm_high_confidence,
      test_vitals_selection,
      test_sensing_confidence_scales,
      test_accuracy_scenarios,
      test_consensus_count,
  ]
  failed = 0
  for t in tests:
      try:
          t()
          print(f"PASS {t.__name__}")
      except Exception as exc:
          failed += 1
          print(f"FAIL {t.__name__}: {exc}")
  if failed:
      sys.exit(1)
  print(f"\nAll {len(tests)} tests passed.")
