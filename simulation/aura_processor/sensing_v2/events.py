"""Fall and distress event detection for sensing_v2.

Informed by techniques described in ESP32-Realtime-System / WiFall
and spatial-ai fall flags, reimplemented for ESP32 CSI in AURA.
"""

from __future__ import annotations

import time

import numpy as np

from .types import DistressEvent


class TargetMotionHistory:
    """Per-target motion score history for collapse signature detection."""

    def __init__(self, maxlen: int = 80):
        self._history: dict[int, list[tuple[float, float]]] = {}
        self._maxlen = maxlen

    def push(self, target_id: int, t_sec: float, motion_score: float) -> None:
        hist = self._history.setdefault(target_id, [])
        hist.append((t_sec, motion_score))
        if len(hist) > self._maxlen:
            self._history[target_id] = hist[-self._maxlen :]

    def detect_fall(
        self,
        target_id: int,
        baseline: float,
        t_sec: float | None = None,
    ) -> DistressEvent | None:
        hist = self._history.get(target_id, [])
        if len(hist) < 12:
            return None

        now = t_sec if t_sec is not None else time.time()
        scores = np.array([s for _, s in hist], dtype=float)
        times = np.array([t for t, _ in hist], dtype=float)
        base = max(baseline, 0.1)

        # Burst then stillness pattern
        recent = scores[-20:]
        if len(recent) < 10:
            return None

        burst_idx = int(np.argmax(recent[:8]))
        burst = float(recent[burst_idx])
        after = recent[burst_idx + 1 :]
        if burst < base * 2.0 or len(after) < 4:
            return None

        stillness = float(np.mean(after)) < base * 0.35
        if not stillness:
            return None

        conf = float(np.clip((burst / (base * 2.0) - 1.0) * 0.4 + 0.35, 0.35, 0.75))
        return DistressEvent(type="fall", timestamp=now, target_id=target_id, confidence=conf)

    def detect_collapse(self, target_id: int, baseline: float, t_sec: float | None = None) -> DistressEvent | None:
        evt = self.detect_fall(target_id, baseline, t_sec)
        if evt is None:
            return None
        evt.type = "collapse"
        return evt


def detect_irregular_breathing(
    resp_history: list[float],
    t_sec: float,
    target_id: int = 0,
) -> DistressEvent | None:
    vals = [r for r in resp_history if 6 <= r <= 40]
    if len(vals) < 5:
        return None
    cv = float(np.std(vals) / (np.mean(vals) + 1e-9))
    if cv < 0.18:
        return None
    conf = float(np.clip(cv * 1.5, 0.35, 0.7))
    return DistressEvent(
        type="irregular_breathing",
        timestamp=t_sec,
        target_id=target_id,
        confidence=conf,
    )


def detect_distress_events(
    target_id: int,
    motion_score: float,
    baseline: float,
    resp_bpm: float,
    resp_history: list[float],
    history: TargetMotionHistory,
    t_sec: float,
) -> list[DistressEvent]:
    history.push(target_id, t_sec, motion_score)
    events: list[DistressEvent] = []

    fall = history.detect_fall(target_id, baseline, t_sec)
    if fall:
        events.append(fall)

    irregular = detect_irregular_breathing(resp_history, t_sec, target_id)
    if irregular:
        events.append(irregular)

    return events
