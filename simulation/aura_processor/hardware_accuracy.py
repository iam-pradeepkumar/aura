"""High-accuracy helpers for live ESP32 multinode sensing."""

from __future__ import annotations

from collections import defaultdict

import numpy as np


class SceneCalibrator:
    """Learn per-node CSI noise floor during an empty-area calibration window."""

    def __init__(self, frames: int = 25, expected_ids: list[int] | None = None):
        self.frames = max(8, frames)
        self.expected_ids = expected_ids or []
        self._history: dict[int, list[float]] = defaultdict(list)
        self._floor: dict[int, float] = {}
        self._ready = False

    def update(self, node_id: int, score: float) -> None:
        if self._ready:
            return
        self._history[node_id].append(float(score))
        if not self.expected_ids:
            return
        counts = [len(self._history.get(nid, [])) for nid in self.expected_ids]
        ready_count = sum(1 for c in counts if c >= self.frames)
        # Finalize when all nodes calibrated, or 75%+ after minimum frames
        if ready_count == len(self.expected_ids):
            self._finalize()
        elif ready_count >= max(2, int(len(self.expected_ids) * 0.75)):
            if min(counts) >= self.frames:
                self._finalize()

    def _finalize(self) -> None:
        for nid, vals in self._history.items():
            if vals:
                self._floor[nid] = float(np.percentile(vals, 72)) + 0.04
        self._ready = True

    @property
    def ready(self) -> bool:
        return self._ready

    @property
    def progress(self) -> float:
        if not self.expected_ids:
            return 1.0 if self._ready else 0.0
        counts = [len(self._history.get(nid, [])) for nid in self.expected_ids]
        return float(min(1.0, min(counts) / self.frames)) if counts else 0.0

    def global_floor(self) -> float:
        if not self._floor:
            return 0.0
        return float(np.median(list(self._floor.values())))

    def motion_threshold(self, node_id: int, base_min: float) -> float:
        floor = self._floor.get(node_id)
        if floor is None:
            return base_min
        return max(base_min, floor * 1.32, floor + 0.08)

    def is_node_motion(self, node_id: int, score: float, base_min: float) -> bool:
        thr = self.motion_threshold(node_id, base_min)
        return score >= thr * 0.96

    def is_empty_scene(self, node_scores: dict[int, float], base_min: float) -> bool:
        """True when all nodes are near calibrated noise floor (empty area)."""
        if not self._ready or not node_scores:
            return False
        for nid, score in node_scores.items():
            thr = self.motion_threshold(nid, base_min)
            if score >= thr * 0.88:
                return False
        return True


def multinode_motion_verdict(
    node_scores: dict[int, float],
    motion_min: float,
    min_nodes: int = 2,
    calibrator: SceneCalibrator | None = None,
) -> dict:
    """Robust motion decision — per-node calibrated thresholds + top-node agreement."""
    min_nodes = int(min_nodes)
    if len(node_scores) < min_nodes:
        return {"motion": False, "active_nodes": 0, "median_score": 0.0, "confidence": 0.0}

    active = 0
    for nid, score in node_scores.items():
        thr = calibrator.motion_threshold(nid, motion_min) if calibrator else motion_min
        if score >= thr * 0.90:
            active += 1

    values = list(node_scores.values())
    sorted_scores = sorted(values, reverse=True)
    top_n = min(min_nodes, len(sorted_scores))
    top_mean = float(np.mean(sorted_scores[:top_n])) if top_n > 0 else 0.0
    med = float(np.median(values))

    # Empty-area guard after calibration
    if calibrator and calibrator.ready and calibrator.is_empty_scene(node_scores, motion_min):
        return {
            "motion": False,
            "active_nodes": active,
            "median_score": med,
            "confidence": 0.08,
        }

    motion = (
        active >= min_nodes
        and top_mean >= motion_min * 0.92
        and med >= motion_min * 0.78
    )
    conf = float(np.clip(
        0.25 * (active / max(len(node_scores), 1))
        + 0.45 * min(top_mean / max(motion_min, 0.1), 1.5)
        + 0.30 * min(med / max(motion_min, 0.1), 1.5),
        0.0, 0.95,
    ))
    return {
        "motion": motion,
        "active_nodes": active,
        "median_score": med,
        "confidence": conf if motion else conf * 0.35,
    }


def merge_cluster_vitals(targets: list[dict]) -> list[dict]:
    """Keep strongest respiration/heartbeat from contributing nodes."""
    out = []
    for t in targets:
        t = dict(t)
        resp = float(t.get("respiration_bpm", 0) or 0)
        hr = float(t.get("heartbeat_bpm", 0) or 0)
        t["respiration_bpm"] = resp
        t["heartbeat_bpm"] = hr
        out.append(t)
    return out


def select_best_vitals(
    node_vitals: list[dict],
    static_only: bool = True,
    max_velocity: float = 0.14,
) -> dict:
    """
    Pick vitals from the node with the strongest phase SNR.
    Prefer nodes seeing a static subject (better for respiration/heartbeat).
    """
    if not node_vitals:
        return {}

    pool = node_vitals
    if static_only:
        static = [v for v in node_vitals if float(v.get("velocity_mps", 0)) <= max_velocity]
        if static:
            pool = static

    def _score(v: dict) -> float:
        rb = float(v.get("respiration_bpm", 0) or 0)
        hb = float(v.get("heartbeat_bpm", 0) or 0)
        mot = float(v.get("motion_score", 0) or 0)
        snr = float(v.get("vitals_snr", 0) or 0)
        valid = (8 <= rb <= 35) + (45 <= hb <= 130)
        return valid * 2.0 + snr * 0.5 + mot * 0.15 + (rb > 0) * 0.3 + (hb > 0) * 0.2

    best = max(pool, key=_score)
    rb = float(best.get("respiration_bpm", 0) or 0)
    hb = float(best.get("heartbeat_bpm", 0) or 0)
    if not (8 <= rb <= 35):
        rb = 0.0
    if not (45 <= hb <= 130):
        hb = 0.0
    return {
        "respiration_bpm": rb,
        "heartbeat_bpm": hb,
        "respiration_waveform": best.get("respiration_waveform") or [],
        "heartbeat_waveform": best.get("heartbeat_waveform") or [],
        "source_node": best.get("node_id"),
    }


def estimate_sensing_confidence(
    target_count: int,
    motion_verdict: dict,
    fused: list[dict],
    calibrator_ready: bool,
) -> float:
    """Overall 0–1 confidence for the current frame (display + gating)."""
    if target_count <= 0:
        return float(motion_verdict.get("confidence", 0)) * 0.25

    votes = [int(t.get("node_votes", 0)) for t in fused]
    confs = [float(t.get("confidence", 0)) for t in fused]
    vote_factor = min(votes) / 4.0 if votes else 0.0
    conf_mean = float(np.mean(confs)) if confs else 0.0
    cal = 0.12 if calibrator_ready else 0.0
    base = 0.35 * vote_factor + 0.45 * conf_mean + 0.12 * motion_verdict.get("confidence", 0) + cal
    return float(np.clip(base, 0.0, 0.96))


def vitals_snr(resp_wave) -> float:
    if resp_wave is None or len(resp_wave) < 8:
        return 0.0
    arr = np.asarray(resp_wave, dtype=float)
    sig = float(np.std(arr))
    noise = float(np.std(np.diff(arr))) + 1e-6
    return float(np.clip(sig / noise, 0.0, 8.0))
