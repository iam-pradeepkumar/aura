#!/usr/bin/env python3
"""Smoke tests for sensing_v2 that avoid heavy aura_processor imports (numpy only)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "aura_processor" / "sensing_v2"


def _load_pkg():
    pkg_name = "aura_processor.sensing_v2"
    if pkg_name not in sys.modules:
        pkg = importlib.util.module_from_spec(
            importlib.util.spec_from_loader(pkg_name, loader=None)
        )
        pkg.__path__ = [str(V2)]  # type: ignore[attr-defined]
        sys.modules[pkg_name] = pkg

    def load(rel: str):
        name = f"{pkg_name}.{rel.replace('.py', '').replace('/', '.')}"
        path = V2 / rel
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        mod.__package__ = pkg_name
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
        return mod

    return load


def main() -> int:
    load = _load_pkg()
    types = load("types.py")
    kalman = load("kalman.py")
    triage = load("triage.py")
    events = load("events.py")

    kf = kalman.Kalman2D()
    x, y, _ = kf.update(1.0, 2.0)
    assert abs(x - 1.0) < 0.01

    tri, conf = triage.suggest_triage(
        resp_bpm=14.0,
        resp_confidence=0.55,
        velocity_mps=0.05,
        is_moving=False,
        presence_confidence=0.6,
        distress_events=[],
        t_sec=0.0,
    )
    assert tri == triage.TRIAGE_DELAYED

    hist = events.TargetMotionHistory()
    t = 0.0
    for s in [0.2, 0.25, 0.3, 1.2, 1.5, 1.8, 0.1, 0.08, 0.05, 0.04, 0.03, 0.02]:
        hist.push(1, t, s)
        t += 0.1
    assert hist.detect_fall(1, 0.3, t) is not None

    evt = types.DistressEvent(type="fall", timestamp=1.0, confidence=0.5)
    tri2, _ = triage.suggest_triage(
        resp_bpm=0,
        resp_confidence=0.0,
        velocity_mps=0.0,
        is_moving=False,
        presence_confidence=0.7,
        distress_events=[evt],
        t_sec=10.0,
    )
    assert tri2 == triage.TRIAGE_IMMEDIATE

    print("sensing_v2 smoke tests: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
