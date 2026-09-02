#!/usr/bin/env python3
"""
AURA Field Live — matplotlib animation with motion trails for 4-corner ESP32 deployment.

Usage:
  1. Start laptop hotspot AURA_HUB / aura2026
  2. Power TX + 4 RX nodes
  3. python tools/field_live.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import matplotlib.animation as animation
import matplotlib.pyplot as plt
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "simulation"))

from aura_processor import AURAPipeline
from aura_processor.hardware_fusion import fuse_hardware_targets, consensus_target_count
from aura_processor.hardware_state import NodePipelineState
from aura_processor.hardware_tracker import FieldTracker
from aura_processor.serialize import target_to_dict
from aura_processor.wireless import DEFAULT_UDP_PORT, WirelessReceiver

PERSON_COLORS = ["#ef4444", "#10b981", "#3b82f6", "#f59e0b", "#a78bfa", "#ec4899"]


def main():
    parser = argparse.ArgumentParser(description="AURA field live map with motion trails")
    parser.add_argument("--port", type=int, default=DEFAULT_UDP_PORT)
    parser.add_argument("--config", default="simulation/config.yaml")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    cfg = yaml.safe_load(cfg_path.read_text()) if cfg_path.exists() else {}
    area = float(cfg.get("area_size_m", 10.0))
    hw_cfg = cfg.get("hardware", {})
    node_pos = {int(k): tuple(v) for k, v in cfg.get("node_positions", {}).items()}

    rx = WirelessReceiver(port=args.port)
    rx.start()
    tracker = FieldTracker(area_size_m=area, trail_len=100)
    node_states: dict[int, NodePipelineState] = {}
    min_pkts = int(hw_cfg.get("min_packets", 30))
    window_pkts = int(hw_cfg.get("window_packets", 60))
    vitals_pkts = int(hw_cfg.get("vitals_window_packets", 120))
    max_people = int(hw_cfg.get("max_people", cfg.get("max_people", 4)))

    def get_state(nid: int) -> NodePipelineState:
        if nid not in node_states:
            pipe = AURAPipeline(
                area_size_m=area,
                motion_threshold=cfg.get("motion_threshold", 0.02),
                max_targets=int(cfg.get("max_people", 8)),
                node_positions=node_pos,
            )
            node_states[nid] = NodePipelineState(
                nid, pipe,
                min_packets=min_pkts,
                refresh_every=int(hw_cfg.get("refresh_every", 30)),
                motion_threshold_scale=float(hw_cfg.get("motion_threshold_scale", 1.0)),
                vitals_packets=vitals_pkts,
                area_margin_m=float(hw_cfg.get("area_margin_m", 0.6)),
                max_per_node=int(hw_cfg.get("max_per_node", 2)),
                min_confidence=float(hw_cfg.get("min_confidence", 0.35)),
            )
        return node_states[nid]

    print("AURA Field Live — motion trails enabled")
    print("Hotspot: AURA_HUB / aura2026  |  UDP", args.port)
    print("Place 4 RX at corners, 1 TX outside perimeter. Ctrl+C to quit.")

    fig = plt.figure(figsize=(14, 8))
    gs = fig.add_gridspec(2, 3, width_ratios=[2, 1, 1])
    ax_map = fig.add_subplot(gs[:, 0])
    ax_count = fig.add_subplot(gs[0, 1])
    ax_vitals = fig.add_subplot(gs[1, 1])
    ax_nodes = fig.add_subplot(gs[:, 2])

    ax_map.set_xlim(-0.5, area + 0.5)
    ax_map.set_ylim(-0.5, area + 0.5)
    ax_map.set_aspect("equal")
    ax_map.set_title("Survivor map — live trails", fontweight="bold")
    ax_map.grid(True, alpha=0.25)
    ax_map.set_xlabel("X (m)")
    ax_map.set_ylabel("Y (m)")

    for nid, (nx, ny) in node_pos.items():
        ax_map.plot(nx, ny, "s", color="#2563eb", markersize=12, zorder=3)
        ax_map.text(nx, ny + 0.3, f"N{nid}", ha="center", fontsize=8, color="#93c5fd")

    trail_lines: dict[int, object] = {}
    marker_artists: dict[int, object] = {}
    count_text = ax_count.text(0.5, 0.55, "0", ha="center", va="center", fontsize=64, fontweight="bold")
    ax_count.text(0.5, 0.2, "people", ha="center", fontsize=14, color="#64748b")
    ax_count.set_title("Count")
    ax_count.axis("off")

    resp_line, = ax_vitals.plot([], [], color="#10b981", linewidth=2)
    ax_vitals.set_title("Respiration")
    ax_vitals.set_xlabel("time (s)")

    status_text = ax_nodes.text(0.02, 0.98, "", va="top", family="monospace", fontsize=9)
    ax_nodes.set_title("Nodes")
    ax_nodes.axis("off")

    t0 = time.time()

    def update(_frame):
        active = rx.active_nodes()
        all_dets: list[dict] = []
        per_node_counts: list[int] = []
        motion_active_nodes = 0
        status_lines = [f"Active nodes: {len(active)}", ""]
        resp_wave = None

        for nid in active:
            win = rx.get_node_window(nid, n=max(window_pkts, vitals_pkts), min_packets=min_pkts)
            link = rx.link_health(nid)
            if win is None:
                status_lines.append(f"  N{nid}: buffering {rx.buffer_length(nid)}/{min_pkts}")
                continue
            csi, ts, rssi = win
            res = get_state(nid).process(csi, ts, rssi)
            if res is None:
                status_lines.append(f"  N{nid}: warming up")
                continue
            for t in res.targets:
                td = target_to_dict(t)
                td["source_node"] = nid
                td["confidence"] = res.confidence
                all_dets.append(td)
            per_node_counts.append(res.target_count)
            if res.motion_detected:
                motion_active_nodes += 1
            if res.respiration_waveform is not None and len(res.respiration_waveform):
                resp_wave = res.respiration_waveform
            status_lines.append(
                f"  N{nid}: {link['status']} {link['packet_rate_hz']:.0f}Hz "
                f"motion={res.motion_detected} n={res.target_count}"
            )

        fused = fuse_hardware_targets(
            all_dets,
            area_size_m=area,
            gate_m=float(hw_cfg.get("fusion_gate_m", 3.5)),
            area_margin_m=float(hw_cfg.get("area_margin_m", 0.4)),
            min_node_votes=int(hw_cfg.get("min_node_votes", 1)),
            min_confidence=float(hw_cfg.get("min_confidence", 0.28)),
            max_people=max_people,
            motion_active_nodes=motion_active_nodes,
        )
        count = consensus_target_count(
            per_node_counts, len(fused), max_people, motion_active_nodes=motion_active_nodes,
        )
        tracked = tracker.update(fused[:count] if count else [], time.time() - t0)

        # Trails
        seen_ids = set()
        for i, t in enumerate(tracked):
            tid = t["id"]
            seen_ids.add(tid)
            color = PERSON_COLORS[(tid - 1) % len(PERSON_COLORS)]
            traj = t.get("trajectory", [])
            if len(traj) > 1:
                xs, ys = zip(*traj)
                if tid not in trail_lines:
                    (trail_lines[tid],) = ax_map.plot(xs, ys, "-", color=color, alpha=0.45, linewidth=2, zorder=1)
                else:
                    trail_lines[tid].set_data(xs, ys)
                    trail_lines[tid].set_color(color)
            sym = "o" if t.get("is_moving") else "^"
            if tid not in marker_artists:
                (marker_artists[tid],) = ax_map.plot(
                    [t["x_m"]], [t["y_m"]], sym, color=color, markersize=14, zorder=5,
                )
            else:
                marker_artists[tid].set_data([t["x_m"]], [t["y_m"]])
                marker_artists[tid].set_marker(sym)

        for tid in list(trail_lines):
            if tid not in seen_ids:
                trail_lines[tid].remove()
                del trail_lines[tid]
                marker_artists[tid].remove()
                del marker_artists[tid]

        count_text.set_text(str(count if count else len(tracked)))
        status_text.set_text("\n".join(status_lines))

        if resp_wave is not None and len(resp_wave):
            t_ax = np.linspace(0, len(resp_wave) / 20.0, len(resp_wave))
            resp_line.set_data(t_ax, resp_wave)
            ax_vitals.relim()
            ax_vitals.autoscale_view()

        return list(trail_lines.values()) + list(marker_artists.values()) + [count_text, status_text, resp_line]

    ani = animation.FuncAnimation(fig, update, interval=250, blit=False)
    try:
        plt.tight_layout()
        plt.show()
    finally:
        rx.stop()


if __name__ == "__main__":
    main()
