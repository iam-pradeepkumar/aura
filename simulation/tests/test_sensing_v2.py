"""Unit tests for sensing_v2 modules."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "simulation"))

from aura_processor.sensing_v2.motion import MotionDebounceFSM, motion_score_v2  # noqa: E402
from aura_processor.sensing_v2.preprocess import preprocess_csi_v2  # noqa: E402
from aura_processor.sensing_v2.triage import suggest_triage, TRIAGE_IMMEDIATE, TRIAGE_DELAYED  # noqa: E402
from aura_processor.sensing_v2.vitals_ensemble import extract_vitals_ensemble  # noqa: E402
from aura_processor.sensing_v2.events import TargetMotionHistory  # noqa: E402
from aura_processor.sensing_v2.kalman import Kalman2D  # noqa: E402


def _synthetic_csi(n: int = 64, sc: int = 52) -> np.ndarray:
    t = np.linspace(0, 3, n)
    phase = 0.3 * np.sin(2 * np.pi * 0.25 * t)
    base = np.exp(1j * phase)
    return np.outer(base, np.ones(sc)) * (1 + 0.05 * np.random.randn(n, sc))


def test_preprocess_v2_shape() -> None:
    csi = _synthetic_csi()
    out, meta = preprocess_csi_v2(csi)
    assert out.shape == csi.shape
    assert meta["weights"] is not None


def test_motion_debounce_fsm() -> None:
    fsm = MotionDebounceFSM(active_hold_frames=2, inactive_hold_frames=2)
    assert not fsm.update(False)
    assert not fsm.update(True)
    assert fsm.update(True)
    assert fsm.update(True)
    assert not fsm.update(False)
    assert fsm.update(False)


def test_motion_score_v2() -> None:
    csi = _synthetic_csi()
    info = motion_score_v2(csi, motion_min=0.5)
    assert "wander" in info
    assert "stability" in info
    assert info["score"] >= 0


def test_vitals_ensemble_still() -> None:
    n, sc = 80, 52
    t = np.linspace(0, 8, n)
    resp = 0.4 * np.sin(2 * np.pi * 0.3 * t)
    csi = np.zeros((n, sc), dtype=complex)
    for i in range(sc):
        csi[:, i] = np.exp(1j * resp) * (1 + 0.02 * np.random.randn(n))
    vitals = extract_vitals_ensemble(csi, fs_hz=20.0, motion_stability=0.7, velocity_mps=0.0)
    assert vitals.quality > 0


def test_triage_immediate_fall() -> None:
    from aura_processor.sensing_v2.types import DistressEvent

    triage, conf = suggest_triage(
        resp_bpm=0,
        resp_confidence=0.0,
        velocity_mps=0.0,
        is_moving=False,
        presence_confidence=0.7,
        distress_events=[DistressEvent(type="fall", timestamp=100.0, confidence=0.6)],
        t_sec=110.0,
    )
    assert triage == TRIAGE_IMMEDIATE
    assert conf > 0.5


def test_triage_delayed_stable_resp() -> None:
    triage, conf = suggest_triage(
        resp_bpm=14.0,
        resp_confidence=0.55,
        velocity_mps=0.05,
        is_moving=False,
        presence_confidence=0.6,
        distress_events=[],
        t_sec=0.0,
    )
    assert triage == TRIAGE_DELAYED
    assert conf > 0.4


def test_fall_detection_history() -> None:
    hist = TargetMotionHistory()
    base = 0.3
    t = 0.0
    for s in [0.2, 0.25, 0.3, 1.2, 1.5, 1.8, 0.1, 0.08, 0.05, 0.04, 0.03, 0.02]:
        hist.push(1, t, s)
        t += 0.1
    evt = hist.detect_fall(1, base, t)
    assert evt is not None
    assert evt.type == "fall"


def test_kalman_2d() -> None:
    kf = Kalman2D()
    x, y, v = kf.update(1.0, 2.0)
    assert abs(x - 1.0) < 0.01
    kf.predict(0.1)
    x2, y2, v2 = kf.update(1.1, 2.1)
    assert abs(x2 - 1.1) < 0.5
