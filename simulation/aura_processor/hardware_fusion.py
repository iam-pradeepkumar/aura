"""Multinode fusion tuned for live ESP32 field deployment (fewer false positives)."""

from __future__ import annotations

import numpy as np


def inside_search_area(
    x: float, y: float, area_size_m: float, margin_m: float = 0.6
) -> bool:
    m = max(0.0, margin_m)
    return m <= x <= area_size_m - m and m <= y <= area_size_m - m


def fuse_hardware_targets(
    target_dicts: list[dict],
    area_size_m: float = 10.0,
    gate_m: float = 2.2,
    area_margin_m: float = 0.6,
    min_node_votes: int = 2,
    min_confidence: float = 0.35,
    max_people: int = 4,
) -> list[dict]:
    """
    Merge per-RX detections with multinode voting.

  - Drop targets outside the search square (with margin).
  - Keep clusters seen by >= min_node_votes RX nodes, or one strong hit near center.
  - Cap total people at max_people.
    """
    if not target_dicts:
        return []

    clusters: list[dict] = []
    for t in target_dicts:
        x, y = float(t["x_m"]), float(t["y_m"])
        if not inside_search_area(x, y, area_size_m, area_margin_m):
            continue
        conf = float(t.get("confidence", 0.4))
        if conf < min_confidence * 0.65:
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
        if votes >= min_node_votes and conf >= min_confidence:
            kept.append(c)
        elif votes >= 1 and conf >= 0.55 and dist_center < area_size_m * 0.38:
            kept.append(c)

    kept.sort(key=lambda c: (len(c.get("_nodes", set())), c.get("confidence", 0)), reverse=True)
    kept = kept[:max_people]

    out: list[dict] = []
    for i, c in enumerate(kept):
        c = dict(c)
        c.pop("_w", None)
        nodes = c.pop("_nodes", set())
        votes = len(nodes) if nodes else 1
        c["id"] = i + 1
        c["node_votes"] = votes
        out.append(c)
    return out


def consensus_target_count(per_node_counts: list[int], fused_len: int, max_people: int) -> int:
    """Conservative global count — avoids inflating from noisy single-node estimates."""
    if fused_len <= 0:
        return 0
    if not per_node_counts:
        return min(fused_len, max_people)
    nz = [c for c in per_node_counts if c > 0]
    if not nz:
        return min(fused_len, max_people)
    median_n = int(np.median(nz))
    return int(np.clip(min(fused_len, median_n, max_people), 0, max_people))
