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
    }


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

    center = area_size_m / 2.0
    kept: list[dict] = []
    for c in clusters:
        votes = len(c.get("_nodes", set()))
        conf = float(c.get("confidence", 0))
        dist_center = float(np.hypot(c["x_m"] - center, c["y_m"] - center))
        moving = bool(c.get("is_moving")) or float(c.get("velocity_mps", 0)) > 0.12

        if votes >= max(min_node_votes, 2) and conf >= min_confidence:
            kept.append(c)
        elif votes >= 1 and moving and conf >= min_confidence * 0.8:
            kept.append(c)
        elif motion_active_nodes >= 2 and votes >= 1 and conf >= min_confidence * 0.65:
            kept.append(c)
        elif votes >= 1 and conf >= 0.5 and dist_center < area_size_m * 0.42:
            kept.append(c)

    if not kept:
        fb = _centroid_fallback(clusters, area_size_m, area_margin_m, motion_active_nodes)
        if fb is not None:
            kept = [fb]

    kept.sort(key=lambda c: (c.get("node_votes", len(c.get("_nodes", set()))), c.get("confidence", 0)), reverse=True)
    kept = kept[:max_people]

    out: list[dict] = []
    for i, c in enumerate(kept):
        c = dict(c)
        c.pop("_w", None)
        nodes = c.pop("_nodes", set())
        votes = c.get("node_votes", len(nodes) if nodes else 1)
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
    """Global count — motion consensus can report 1 even when fusion is conservative."""
    if fused_len <= 0:
        if motion_active_nodes >= 2:
            return 1
        return 0
    if not per_node_counts:
        return min(fused_len, max_people)
    nz = [c for c in per_node_counts if c > 0]
    if not nz:
        return min(fused_len, max_people)
    median_n = int(np.median(nz))
    base = min(fused_len, median_n, max_people)
    if base <= 0 and motion_active_nodes >= 2:
        return 1
    return int(np.clip(base, 0, max_people))
