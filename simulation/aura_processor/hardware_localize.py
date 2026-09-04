"""Live ESP32 positioning — RSSI proximity + corner geometry correction."""

from __future__ import annotations

import numpy as np


def inward_reference(
    nx: float, ny: float, area_size_m: float, blend: float = 0.38
) -> tuple[float, float]:
    """Point slightly inside the search area from a corner node."""
    cx, cy = area_size_m / 2.0, area_size_m / 2.0
    return nx + blend * (cx - nx), ny + blend * (cy - ny)


def rssi_localize(
    rssi_by_node: dict[int, float],
    node_positions: dict[int, tuple[float, float]],
    area_size_m: float,
    margin_m: float = 0.35,
) -> tuple[float, float] | None:
    """
    Coarse live position from RSSI — strongest signal = nearest corner sector.
    Much more reliable than raw CSI AoA on ESP32 outdoors.
    """
    if len(rssi_by_node) < 1:
        return None

    rmax = max(rssi_by_node.values())
    weights: dict[int, float] = {}
    for nid, rssi in rssi_by_node.items():
        if nid not in node_positions:
            continue
        weights[nid] = float(np.exp((float(rssi) - rmax) / 5.5))

    wsum = float(sum(weights.values()))
    if wsum <= 0:
        return None

    x, y = 0.0, 0.0
    for nid, w in weights.items():
        nx, ny = node_positions[nid]
        rx, ry = inward_reference(nx, ny, area_size_m)
        x += w * rx
        y += w * ry
    x /= wsum
    y /= wsum

    m = max(0.0, margin_m)
    return (
        float(np.clip(x, m, area_size_m - m)),
        float(np.clip(y, m, area_size_m - m)),
    )


def constrain_from_corner(
    x: float,
    y: float,
    sensor_xy: tuple[float, float],
    area_size_m: float,
    margin_m: float = 0.35,
) -> tuple[float, float]:
    """Keep per-node CSI hits on the inward side of a perimeter RX."""
    sx, sy = sensor_xy
    m = max(0.0, margin_m)
    a = area_size_m

    if sx <= a * 0.15:
        x = max(x, sx + m)
    elif sx >= a * 0.85:
        x = min(x, sx - m)

    if sy <= a * 0.15:
        y = max(y, sy + m)
    elif sy >= a * 0.85:
        y = min(y, sy - m)

    return (
        float(np.clip(x, m, a - m)),
        float(np.clip(y, m, a - m)),
    )


def fix_diagonal_mirror(
    x: float,
    y: float,
    sensor_xy: tuple[float, float],
    area_size_m: float,
) -> tuple[float, float]:
    """
    ESP32 CSI AoA often places targets near the opposite corner.
    Mirror through area center when the hit is closer to the far corner.
    """
    sx, sy = sensor_xy
    a = area_size_m
    opp_x, opp_y = a - sx, a - sy
    d_own = float(np.hypot(x - sx, y - sy))
    d_opp = float(np.hypot(x - opp_x, y - opp_y))
    if d_opp < d_own * 0.92 and d_own > 2.0:
        return float(a - x), float(a - y)
    return x, y


def refine_detection_xy(
    det: dict,
    sensor_xy: tuple[float, float],
    area_size_m: float,
    margin_m: float = 0.35,
) -> dict:
    """Apply corner constraints + diagonal mirror fix to one detection."""
    x = float(det["x_m"])
    y = float(det["y_m"])
    x, y = fix_diagonal_mirror(x, y, sensor_xy, area_size_m)
    x, y = constrain_from_corner(x, y, sensor_xy, area_size_m, margin_m)
    out = dict(det)
    out["x_m"] = x
    out["y_m"] = y
    return out


def blend_live_position(
    csi_xy: tuple[float, float] | None,
    rssi_xy: tuple[float, float] | None,
    csi_conf: float = 0.4,
    moving: bool = True,
) -> tuple[float, float] | None:
    """Fuse CSI and RSSI — RSSI dominates when moving for responsive live tracking."""
    if rssi_xy is None and csi_xy is None:
        return None
    if rssi_xy is None:
        return csi_xy
    if csi_xy is None:
        return rssi_xy

    if moving:
        w_rssi = 0.65
    else:
        w_rssi = 0.50
    w_rssi = float(np.clip(w_rssi + (csi_conf - 0.4) * 0.25, 0.40, 0.80))
    w_csi = 1.0 - w_rssi
    x = w_rssi * rssi_xy[0] + w_csi * csi_xy[0]
    y = w_rssi * rssi_xy[1] + w_csi * csi_xy[1]
    return x, y


def refine_fused_targets(
    targets: list[dict],
    rssi_by_node: dict[int, float],
    node_positions: dict[int, tuple[float, float]],
    area_size_m: float,
    margin_m: float = 0.35,
) -> list[dict]:
    """Apply RSSI-guided position refinement to fused targets (never invent targets)."""
    if not targets:
        return []

    rssi_xy = rssi_localize(rssi_by_node, node_positions, area_size_m, margin_m)
    n_rssi = len(rssi_by_node)
    out: list[dict] = []
    for t in targets:
        t = dict(t)
        csi_xy = (float(t["x_m"]), float(t["y_m"]))
        conf = float(t.get("confidence", 0.4))
        moving = bool(t.get("is_moving")) or float(t.get("velocity_mps", 0)) > 0.1
        blended = blend_live_position(csi_xy, rssi_xy, conf, moving)
        if blended is not None:
            # Trust RSSI more when 3+ nodes contribute (better trilateration)
            if n_rssi >= 3 and rssi_xy is not None:
                w = 0.55 if moving else 0.62
                blended = (
                    w * rssi_xy[0] + (1 - w) * blended[0],
                    w * rssi_xy[1] + (1 - w) * blended[1],
                )
            t["x_m"] = round(blended[0], 3)
            t["y_m"] = round(blended[1], 3)
        out.append(t)
    return out
