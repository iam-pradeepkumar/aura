#!/usr/bin/env python3
"""
AURA Wireless Hub — receive CSI from ALL ESP32 nodes over WiFi (no USB cables).

1. Start laptop hotspot: SSID=AURA_HUB, password=aura2026
2. Set laptop IP to 192.168.4.1 (default on most hotspots)
3. Flash aura_rx on all nodes with unique NODE_ID
4. Run: python tools/wireless_hub.py
"""

from __future__ import annotations

import argparse
import sys
import threading
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "simulation"))

from aura_processor import AURAPipeline
from aura_processor.hardware_fusion import fuse_hardware_targets, consensus_target_count
from aura_processor.hardware_state import NodePipelineState
from aura_processor.wireless import DEFAULT_UDP_PORT, WirelessReceiver


def main():
    parser = argparse.ArgumentParser(description="AURA wireless laptop hub")
    parser.add_argument("--port", type=int, default=DEFAULT_UDP_PORT)
    parser.add_argument("--config", default="simulation/config.yaml")
    args = parser.parse_args()

    cfg_path = Path(args.config)
    cfg = {}
    if cfg_path.exists():
        with cfg_path.open() as f:
            cfg = yaml.safe_load(f) or {}

    area = cfg.get("area_size_m", 10.0)
    hw_cfg = cfg.get("hardware", {})
    node_pos = {int(k): tuple(v) for k, v in cfg.get("node_positions", {}).items()}
    pipeline = AURAPipeline(
        area_size_m=area,
        motion_threshold=cfg.get("motion_threshold", 0.02),
        max_targets=int(cfg.get("max_people", 8)),
        node_positions=node_pos,
    )

    rx = WirelessReceiver(port=args.port)
    rx.start()
    node_states: dict[int, NodePipelineState] = {}

    def get_state(nid: int) -> NodePipelineState:
        if nid not in node_states:
            node_states[nid] = NodePipelineState(
                nid,
                pipeline,
                min_packets=min_pkts,
                refresh_every=int(hw_cfg.get("refresh_every", 30)),
                motion_threshold_scale=float(hw_cfg.get("motion_threshold_scale", 1.0)),
                vitals_packets=vitals_pkts,
                area_margin_m=float(hw_cfg.get("area_margin_m", 0.6)),
                max_per_node=int(hw_cfg.get("max_per_node", 2)),
                min_confidence=float(hw_cfg.get("min_confidence", 0.35)),
            )
        return node_states[nid]

    print(f"Listening on UDP :{args.port}")
    print("Start laptop hotspot: SSID=AURA_HUB  password=aura2026")
    print("Power on all ESP32 RX nodes — results appear live below.")

    fig, axes = plt.subplots(2, 2, figsize=(12, 9))
    fig.suptitle("AURA Wireless Hub — Outdoor Field", fontweight="bold")
    ax_map, ax_count, ax_resp, ax_nodes = axes[0, 0], axes[0, 1], axes[1, 0], axes[1, 1]

    ax_map.set_xlim(0, area)
    ax_map.set_ylim(0, area)
    ax_map.set_aspect("equal")
    ax_map.set_title("Survivor Map (CSI)")
    ax_map.grid(True, alpha=0.3)
    for nid, (nx, ny) in node_pos.items():
        ax_map.plot(nx, ny, "s", color="#2563eb", markersize=10)
    scatter = ax_map.scatter([], [], c="#ef4444", s=150, zorder=5)

    count_text = ax_count.text(0.5, 0.5, "0", ha="center", va="center", fontsize=56, fontweight="bold")
    ax_count.set_title("People Count")
    ax_count.axis("off")

    resp_line, = ax_resp.plot([], [], color="#10b981")
    ax_resp.set_title("Respiration / Heartbeat")
    ax_resp.set_xlabel("Time (s)")

    node_status = ax_nodes.text(0.05, 0.95, "", va="top", family="monospace", fontsize=10)
    ax_nodes.set_title("Node Status (wireless)")
    ax_nodes.axis("off")

    window_pkts = int(hw_cfg.get("window_packets", 60))
    vitals_pkts = int(hw_cfg.get("vitals_window_packets", 120))
    min_pkts = int(hw_cfg.get("min_packets", 30))
    max_people = int(hw_cfg.get("max_people", cfg.get("max_people", 4)))

    def update(_):
        active = rx.active_nodes()
        all_target_dicts = []
        per_node_counts: list[int] = []
        resp_waves = []
        status_lines = [f"Active nodes: {len(active)}", ""]

        for nid in active:
            win = rx.get_node_window(nid, n=max(window_pkts, vitals_pkts), min_packets=min_pkts)
            link = rx.link_health(nid)
            if win is None:
                status_lines.append(f"  Node {nid}: buffering ({rx.buffer_length(nid)})")
                continue
            csi, ts = win
            res = get_state(nid).process(csi, ts)
            if res is None:
                status_lines.append(f"  Node {nid}: warming up")
                continue
            for t in res.targets:
                td = {"x_m": t.x_m, "y_m": t.y_m, "confidence": res.confidence, "source_node": nid}
                all_target_dicts.append(td)
            per_node_counts.append(res.target_count)
            if res.respiration_waveform is not None and len(res.respiration_waveform):
                resp_waves.append(res.respiration_waveform)
            status_lines.append(
                f"  Node {nid}: {link['status']} | {link['packet_rate_hz']:.0f} Hz | "
                f"motion={res.motion_detected} count={res.target_count} "
                f"resp={res.respiration_bpm:.0f} HR={res.heartbeat_bpm:.0f}"
            )

        fused = fuse_hardware_targets(
            all_target_dicts,
            area_size_m=area,
            gate_m=float(hw_cfg.get("fusion_gate_m", 2.2)),
            area_margin_m=float(hw_cfg.get("area_margin_m", 0.6)),
            min_node_votes=int(hw_cfg.get("min_node_votes", 2)),
            min_confidence=float(hw_cfg.get("min_confidence", 0.35)),
            max_people=max_people,
        )
        count = consensus_target_count(per_node_counts, len(fused), max_people)
        if fused:
            scatter.set_offsets(np.c_[ [t["x_m"] for t in fused], [t["y_m"] for t in fused] ])
        else:
            scatter.set_offsets(np.empty((0, 2)))

        count_text.set_text(str(count))
        node_status.set_text("\n".join(status_lines) if status_lines else "Waiting for nodes...")

        if resp_waves:
            wave = resp_waves[0]
            t_ax = np.linspace(0, len(wave) / 20.0, len(wave))
            resp_line.set_data(t_ax, wave)
            ax_resp.relim()
            ax_resp.autoscale_view()

        return [scatter, count_text, resp_line, node_status]

    ani = animation.FuncAnimation(fig, update, interval=250, blit=False)
    try:
        plt.show()
    finally:
        rx.stop()


if __name__ == "__main__":
    main()
