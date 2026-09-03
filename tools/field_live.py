#!/usr/bin/env python3
"""
AURA Field Live — local matplotlib dashboard for ESP32 outdoor CSI sensing.

Run this on your laptop (not the web dashboard). Listens on UDP :5555.

  1. Laptop hotspot: AURA_HUB / aura2026
  2. Power TX probe, then 4 RX nodes (unique NODE_ID 1–4)
  3. python3 tools/field_live.py

Close the web dashboard first — only one process can bind UDP 5555.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "simulation"))

from aura_processor.hardware_live import LiveFieldEngine, load_field_config, PROCESSOR_VERSION
from aura_processor.wireless import DEFAULT_UDP_PORT

# Dark theme — operator console aesthetic
plt.style.use("dark_background")
BG = "#0b1120"
PANEL = "#111827"
GRID = "#1f2937"
ACCENT = "#3b82f6"
MOTION = "#ef4444"
STATIC = "#f59e0b"
RESP = "#10b981"
HR = "#f43f5e"
PERSON_COLORS = ["#ef4444", "#10b981", "#3b82f6", "#f59e0b", "#a78bfa", "#ec4899"]


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA local field live sensing (matplotlib)")
    parser.add_argument("--port", type=int, default=DEFAULT_UDP_PORT)
    parser.add_argument("--config", default="simulation/config.yaml")
    parser.add_argument("--fps", type=float, default=12.0, help="Display refresh rate")
    args = parser.parse_args()

    cfg = load_field_config(args.config)
    area = float(cfg.get("area_size_m", 10.0))
    node_pos = {int(k): tuple(v) for k, v in cfg.get("node_positions", {}).items()}

    try:
        engine = LiveFieldEngine(cfg, port=args.port)
        engine.start()
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Stop the web dashboard and udp_probe.py — only one UDP listener on :5555.", file=sys.stderr)
        sys.exit(1)

    snapshot: dict = {}
    snap_lock = threading.Lock()
    running = True

    def worker() -> None:
        nonlocal snapshot
        interval = 0.1  # 10 Hz sensing
        while running:
            try:
                frame = engine.process_frame()
            except Exception as exc:
                frame = {"error": str(exc), "active_nodes": 0, "expected_nodes": 4, "targets": [], "target_count": 0}
            with snap_lock:
                snapshot = frame
            time.sleep(interval)

    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()

    print("AURA Field Live", PROCESSOR_VERSION)
    print(f"UDP :{args.port}  |  Hotspot AURA_HUB / aura2026")
    print("Walk inside the search area. Stand still for vitals. Ctrl+C to quit.\n")

    fig = plt.figure(figsize=(15, 8.5), facecolor=BG)
    fig.canvas.manager.set_window_title("AURA Field Live")  # type: ignore[union-attr]
    gs = fig.add_gridspec(3, 4, height_ratios=[0.08, 1.2, 1.0], width_ratios=[2.2, 0.9, 0.9, 1.1], hspace=0.32, wspace=0.28)

    # Title bar
    ax_title = fig.add_subplot(gs[0, :])
    ax_title.axis("off")
    title_text = ax_title.text(0.01, 0.5, "AURA — Field Sensing", fontsize=14, fontweight="bold", color="#f8fafc", va="center")
    status_text = ax_title.text(0.99, 0.5, "Starting…", fontsize=10, color="#94a3b8", va="center", ha="right", family="monospace")

    # Map
    ax_map = fig.add_subplot(gs[1, 0])
    ax_map.set_facecolor(PANEL)
    ax_map.set_xlim(-0.3, area + 0.3)
    ax_map.set_ylim(-0.3, area + 0.3)
    ax_map.set_aspect("equal")
    ax_map.set_title("Survivor map", color="#e2e8f0", fontsize=11, pad=8)
    ax_map.grid(True, color=GRID, alpha=0.6, linewidth=0.6)
    ax_map.set_xlabel("X (m)", color="#64748b", fontsize=9)
    ax_map.set_ylabel("Y (m)", color="#64748b", fontsize=9)
    ax_map.tick_params(colors="#64748b", labelsize=8)

    for nid, (nx, ny) in node_pos.items():
        ax_map.plot(nx, ny, "s", color=ACCENT, markersize=11, zorder=4, markeredgecolor="#1e3a8a", markeredgewidth=1)
        ax_map.text(nx, ny - 0.45, f"N{nid}", ha="center", fontsize=8, color="#93c5fd", zorder=4)

    # search area border
    rect = plt.Rectangle((0, 0), area, area, fill=False, edgecolor="#334155", linewidth=1.5, linestyle="--", zorder=1)
    ax_map.add_patch(rect)

    trail_lines: dict[int, object] = {}
    marker_artists: dict[int, object] = {}

    # Stats column
    ax_count = fig.add_subplot(gs[1, 1])
    ax_count.set_facecolor(PANEL)
    ax_count.axis("off")
    count_num = ax_count.text(0.5, 0.62, "0", ha="center", va="center", fontsize=52, fontweight="bold", color="#f8fafc")
    ax_count.text(0.5, 0.28, "PEOPLE", ha="center", fontsize=10, color="#64748b", fontweight="600")
    motion_badge = ax_count.text(0.5, 0.08, "STATIC", ha="center", fontsize=11, color=STATIC, fontweight="bold")

    ax_motion = fig.add_subplot(gs[1, 2])
    ax_motion.set_facecolor(PANEL)
    ax_motion.axis("off")
    ax_motion.text(0.5, 0.85, "VITALS", ha="center", fontsize=10, color="#64748b", fontweight="600")
    resp_val = ax_motion.text(0.5, 0.58, "—", ha="center", fontsize=22, color=RESP, fontweight="bold")
    ax_motion.text(0.5, 0.48, "Resp BPM", ha="center", fontsize=8, color="#64748b")
    hr_val = ax_motion.text(0.5, 0.22, "—", ha="center", fontsize=22, color=HR, fontweight="bold")
    ax_motion.text(0.5, 0.12, "Heart BPM", ha="center", fontsize=8, color="#64748b")

    ax_nodes = fig.add_subplot(gs[1, 3])
    ax_nodes.set_facecolor(PANEL)
    ax_nodes.axis("off")
    ax_nodes.set_title("Nodes", color="#e2e8f0", fontsize=10, pad=6)
    nodes_body = ax_nodes.text(0.02, 0.95, "", va="top", family="monospace", fontsize=8.5, color="#cbd5e1")

    # Waveforms
    ax_resp = fig.add_subplot(gs[2, :2])
    ax_resp.set_facecolor(PANEL)
    resp_line, = ax_resp.plot([], [], color=RESP, linewidth=1.8)
    ax_resp.set_title("Respiration waveform", color="#e2e8f0", fontsize=10)
    ax_resp.set_xlabel("Time (s)", color="#64748b", fontsize=8)
    ax_resp.tick_params(colors="#64748b", labelsize=8)
    ax_resp.grid(True, color=GRID, alpha=0.5)

    ax_hr = fig.add_subplot(gs[2, 2:])
    ax_hr.set_facecolor(PANEL)
    hr_line, = ax_hr.plot([], [], color=HR, linewidth=1.8)
    ax_hr.set_title("Heartbeat waveform", color="#e2e8f0", fontsize=10)
    ax_hr.set_xlabel("Time (s)", color="#64748b", fontsize=8)
    ax_hr.tick_params(colors="#64748b", labelsize=8)
    ax_hr.grid(True, color=GRID, alpha=0.5)

    t0 = time.time()

    def draw(_frame: int) -> list:
        with snap_lock:
            d = dict(snapshot) if snapshot else {}

        if d.get("error"):
            status_text.set_text(f"ERROR: {d['error'][:60]}")
            return []

        online = d.get("linked_nodes", d.get("active_nodes", 0))
        sensing = d.get("sensing_nodes", 0)
        expected = d.get("expected_nodes", 4)
        pkts = d.get("total_packets", 0)
        status_text.set_text(
            f"v{PROCESSOR_VERSION}  |  linked {online}/{expected}  sensing {sensing}/{expected}  |  pkts {pkts}  |  "
            f"{'MOTION' if d.get('motion_detected') else 'static'}"
        )

        count = d.get("target_count", 0)
        count_num.set_text(str(count))
        if d.get("motion_detected"):
            motion_badge.set_text("MOTION")
            motion_badge.set_color(MOTION)
        else:
            motion_badge.set_text("STATIC")
            motion_badge.set_color(STATIC)

        rb = d.get("respiration_bpm", 0)
        hb = d.get("heartbeat_bpm", 0)
        resp_val.set_text(f"{rb:.0f}" if rb else "—")
        hr_val.set_text(f"{hb:.0f}" if hb else "—")

        lines = []
        for n in d.get("node_status", []):
            st = n.get("status", "?")
            hz = n.get("packet_rate_hz", 0)
            mot = "M" if n.get("motion") else "·"
            sc = n.get("motion_score", "")
            sc_s = f" m={sc}" if sc != "" else ""
            buf = n.get("buffer", "")
            buf_s = f" buf={buf}" if buf != "" else ""
            lines.append(f"N{n['id']} {st:14} {hz:4.0f}Hz {mot}{sc_s}{buf_s}")
        nodes_body.set_text("\n".join(lines) if lines else "Waiting for CSI…")

        warnings = d.get("warnings") or []
        if warnings and not lines:
            nodes_body.set_text("\n".join(warnings[:2]))

        tracked = d.get("targets", [])
        seen: set[int] = set()
        for i, t in enumerate(tracked):
            tid = int(t["id"])
            seen.add(tid)
            color = PERSON_COLORS[(tid - 1) % len(PERSON_COLORS)]
            traj = t.get("trajectory", [])
            if len(traj) > 1:
                xs, ys = zip(*traj)
                if tid not in trail_lines:
                    (trail_lines[tid],) = ax_map.plot(xs, ys, "-", color=color, alpha=0.5, linewidth=2.2, zorder=2)
                else:
                    trail_lines[tid].set_data(xs, ys)
            sym = "o" if t.get("is_moving") else "^"
            ms = 13 if t.get("is_moving") else 11
            if tid not in marker_artists:
                (marker_artists[tid],) = ax_map.plot(
                    [t["x_m"]], [t["y_m"]], sym, color=color, markersize=ms, zorder=6,
                    markeredgecolor="white", markeredgewidth=0.6,
                )
            else:
                marker_artists[tid].set_data([t["x_m"]], [t["y_m"]])
                marker_artists[tid].set_marker(sym)
                marker_artists[tid].set_markersize(ms)

        for tid in list(trail_lines):
            if tid not in seen:
                trail_lines[tid].remove()
                del trail_lines[tid]
                marker_artists[tid].remove()
                del marker_artists[tid]

        fs = 20.0
        rw = d.get("respiration_waveform") or []
        hw = d.get("heartbeat_waveform") or []
        if len(rw):
            tx = np.linspace(0, len(rw) / fs, len(rw))
            resp_line.set_data(tx, rw)
            ax_resp.relim()
            ax_resp.autoscale_view()
        if len(hw):
            tx = np.linspace(0, len(hw) / fs, len(hw))
            hr_line.set_data(tx, hw)
            ax_hr.relim()
            ax_hr.autoscale_view()

        return list(trail_lines.values()) + list(marker_artists.values())

    interval_ms = int(1000 / max(args.fps, 4))
    _ani = animation.FuncAnimation(fig, draw, interval=interval_ms, blit=False, cache_frame_data=False)

    try:
        plt.tight_layout()
        plt.show()
    except KeyboardInterrupt:
        pass
    finally:
        running = False
        worker_thread.join(timeout=1.0)
        engine.stop()


if __name__ == "__main__":
    main()
