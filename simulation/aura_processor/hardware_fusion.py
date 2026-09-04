"""Multinode fusion tuned for live ESP32 field deployment."""

from __future__ import annotations

import numpy as np


def inside_search_area(
    x: float, y: float, area_size_m: float, margin_m: float = 0.4
) -> bool:
    m = max(0.0, margin_m)
    return m <= x <= area_size_m - m and m <= y <= area_size_m - m


def _centroid_fallback(
    clusters: list[dict],
    area_size_m: float,
    area_margin_m: float,
    motion_active_nodes: int,
) -> dict | None:
    """When several nodes see motion but XY estimates disagree, fuse to one centroid."""
    if motion_active_nodes < 2 or not clusters:
        return None

    xs, ys, ws = [], [], []
    for c in clusters:
        x, y = float(c["x_m"]), float(c["y_m"])
        if not inside_search_area(x, y, area_size_m, area_margin_m):
            continue
        w = float(c.get("confidence", 0.3)) * max(len(c.get("_nodes", set())), 1)
        xs.append(x * w)
        ys.append(y * w)
        ws.append(w)

    if not ws:
        return None

    wsum = float(sum(ws))
    return {
        "x_m": float(sum(xs) / wsum),
        "y_m": float(sum(ys) / wsum),
        "velocity_mps": max(float(c.get("velocity_mps", 0)) for c in clusters),
        "confidence": float(np.clip(wsum / max(motion_active_nodes, 1) * 0.35, 0.32, 0.72)),
        "is_moving": any(c.get("is_moving") for c in clusters),
        "respiration_bpm": max(float(c.get("respiration_bpm", 0)) for c in clusters),
        "heartbeat_bpm": max(float(c.get("heartbeat_bpm", 0)) for c in clusters),
        "respiration_waveform": next(
            (c["respiration_waveform"] for c in clusters if c.get("respiration_waveform")), None
        ),
        "heartbeat_waveform": next(
            (c["heartbeat_waveform"] for c in clusters if c.get("heartbeat_waveform")), None
        ),
        "node_votes": min(motion_active_nodes, 4),
        "motion_consensus": True,
    }


def fuse_motion_consensus(
    node_scores: dict[int, float],
    node_positions: dict[int, tuple[float, float]],
    area_size_m: float,
    margin_m: float = 0.35,
    motion_min: float = 0.52,
    min_nodes: int = 2,
    node_thresholds: dict[int, float] | None = None,
) -> list[dict]:
    """
    When 2+ nodes see strong CSI motion but localization returned nothing,
    estimate one person at the motion-weighted centroid of inward node bearings.
    """
    from .hardware_localize import inward_reference

    active = []
    for nid, score in node_scores.items():
        if nid not in node_positions:
            continue
        thr = float(node_thresholds.get(nid, motion_min)) if node_thresholds else motion_min
        if float(score) >= thr * 0.86:
            active.append((nid, float(score)))
    if len(active) < min_nodes:
        return []

    scores = [s for _, s in active]
    if float(np.median(scores)) < motion_min * 0.92:
        return []

    xs, ys, ws = [], [], []
    for nid, score in active:
        nx, ny = node_positions[nid]
        rx, ry = inward_reference(nx, ny, area_size_m)
        m = max(0.0, margin_m)
        rx = float(np.clip(rx, m, area_size_m - m))
        ry = float(np.clip(ry, m, area_size_m - m))
        xs.append(rx * score)
        ys.append(ry * score)
        ws.append(score)

    wsum = float(sum(ws))
    if wsum <= 0:
        return []

    conf = float(np.clip(0.36 + 0.09 * len(active) + 0.04 * (np.median(scores) - motion_min), 0.38, 0.68))
    return [{
        "id": 1,
        "x_m": round(float(sum(xs) / wsum), 3),
        "y_m": round(float(sum(ys) / wsum), 3),
        "velocity_mps": 0.22,
        "confidence": round(conf, 2),
        "is_moving": True,
        "node_votes": len(active),
        "motion_consensus": True,
        "respiration_bpm": 0.0,
        "heartbeat_bpm": 0.0,
    }]


def fuse_hardware_targets(
    target_dicts: list[dict],
    area_size_m: float = 10.0,
    gate_m: float = 3.5,
    area_margin_m: float = 0.4,
    min_node_votes: int = 1,
    min_confidence: float = 0.28,
    max_people: int = 4,
    motion_active_nodes: int = 0,
) -> list[dict]:
    """
    Merge per-RX detections with multinode voting and motion consensus.

    Corner nodes often localize the same walker to different XY — use a wide gate
    and centroid fallback when multiple nodes report motion.
    """
    if not target_dicts:
        return []

    clusters: list[dict] = []
    for t in target_dicts:
        x, y = float(t["x_m"]), float(t["y_m"])
        if not inside_search_area(x, y, area_size_m, area_margin_m):
            continue
        conf = float(t.get("confidence", 0.4))
        if conf < min_confidence * 0.5:
            continue

        merged = False
        for c in clusters:
            d = (x - c["x_m"]) ** 2 + (y - c["y_m"]) ** 2
            if d < gate_m * gate_m:
                w = max(conf, 0.1)
                n = c.get("_w", 1.0)
                c["x_m"] = (c["x_m"] * n + x * w) / (n + w)
                c["y_m"] = (c["y_m"] * n + y * w) / (n + w)
                c["_w"] = n + w
                nodes = c.setdefault("_nodes", set())
                if t.get("source_node") is not None:
                    nodes.add(int(t["source_node"]))
                c["velocity_mps"] = max(c.get("velocity_mps", 0), float(t.get("velocity_mps", 0)))
                c["respiration_bpm"] = max(c.get("respiration_bpm", 0), float(t.get("respiration_bpm", 0)))
                c["heartbeat_bpm"] = max(c.get("heartbeat_bpm", 0), float(t.get("heartbeat_bpm", 0)))
                c["is_moving"] = c.get("is_moving") or t.get("is_moving")
                c["confidence"] = max(c.get("confidence", 0), conf)
                if t.get("respiration_waveform"):
                    c["respiration_waveform"] = t["respiration_waveform"]
                if t.get("heartbeat_waveform"):
                    c["heartbeat_waveform"] = t["heartbeat_waveform"]
                merged = True
                break
        if not merged:
            nodes = set()
            if t.get("source_node") is not None:
                nodes.add(int(t["source_node"]))
            clusters.append({
                **t,
                "x_m": x,
                "y_m": y,
                "_w": max(conf, 0.1),
                "_nodes": nodes,
                "confidence": conf,
            })

    kept: list[dict] = []
    for c in clusters:
        votes = len(c.get("_nodes", set()))
        conf = float(c.get("confidence", 0))

        if votes >= max(min_node_votes, 2) and conf >= min_confidence:
            kept.append(c)
        elif votes >= 2 and conf >= min_confidence * 0.88:
            kept.append(c)
        elif votes >= 1 and conf >= min_confidence * 1.05 and motion_active_nodes >= 2:
            kept.append(c)

    if not kept and motion_active_nodes >= 2:
        fb = _centroid_fallback(clusters, area_size_m, area_margin_m, motion_active_nodes)
        if fb is not None and float(fb.get("confidence", 0)) >= min_confidence * 0.85:
            kept = [fb]

    kept.sort(key=lambda c: (len(c.get("_nodes", set())), c.get("confidence", 0)), reverse=True)
    kept = kept[:max_people]

    out: list[dict] = []
    for i, c in enumerate(kept):
        c = dict(c)
        c.pop("_w", None)
        nodes = c.pop("_nodes", set())
        votes = len(nodes) if nodes else 0
        c["id"] = i + 1
        c["node_votes"] = votes
        out.append(c)
    return out


def consensus_target_count(
    per_node_counts: list[int],
    fused_len: int,
    max_people: int,
    motion_active_nodes: int = 0,
) -> int:
    """Global count aligned with fused targets and per-node estimates."""
    if fused_len <= 0:
        return 0
    if not per_node_counts:
        return min(fused_len, max_people)
    nz = [c for c in per_node_counts if c > 0]
    if not nz:
        return min(fused_len, max_people)
    median_n = int(np.median(nz))
    return int(np.clip(min(fused_len, median_n, max_people), 0, max_people))
