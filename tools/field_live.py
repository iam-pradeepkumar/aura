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
import matplotlib.patches as mpatches
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "simulation"))

from aura_processor.hardware_live import LiveFieldEngine, load_field_config, PROCESSOR_VERSION
from aura_processor.wireless import DEFAULT_UDP_PORT

# Playful Geometric palette
BG = "#FFFDF5"
FG = "#1E293B"
MUTED = "#64748B"
BORDER = "#1E293B"
ACCENT = "#8B5CF6"
SECONDARY = "#F472B6"
TERTIARY = "#FBBF24"
QUAT = "#34D399"
PANEL = "#FFFFFF"
GRID = "#E2E8F0"
PERSON_COLORS = [SECONDARY, QUAT, ACCENT, TERTIARY, "#60A5FA", "#FB923C"]


def _panel_ax(ax, title: str = "") -> None:
    """Sticker-style panel axes."""
    ax.set_facecolor(PANEL)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color(BORDER)
        spine.set_linewidth(2)
    if title:
        ax.set_title(title, color=FG, fontsize=11, fontweight="bold", pad=8)


def _chart_ax(ax, title: str, xlabel: str = "") -> None:
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color(BORDER)
        spine.set_linewidth(2)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.set_title(title, color=FG, fontsize=11, fontweight="bold", pad=8)
    ax.grid(True, color=GRID, alpha=0.9, linewidth=1)
    if xlabel:
        ax.set_xlabel(xlabel, color=MUTED, fontsize=9)


def _resolve_config(path: str) -> str:
    p = Path(path)
    if not p.is_absolute():
        p = REPO_ROOT / p
    return str(p)


def _format_node_lines(node_status: list[dict], expected: int) -> str:
    if not node_status:
        return "\n".join(f"N{i}  waiting…" for i in range(1, expected + 1))
    lines = []
    for n in node_status:
        nid = n.get("id", "?")
        st = str(n.get("status", "?"))[:16]
        hz = float(n.get("packet_rate_hz") or 0)
        mot = "●" if n.get("motion") else "○"
        sc = n.get("motion_score", "")
        sc_s = f" m={sc}" if sc != "" else ""
        lines.append(f"N{nid} {st:16} {hz:4.0f}Hz {mot}{sc_s}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA local field live sensing (matplotlib)")
    parser.add_argument("--port", type=int, default=DEFAULT_UDP_PORT)
    parser.add_argument("--config", default="simulation/config.yaml")
    parser.add_argument("--fps", type=float, default=12.0, help="Display refresh rate")
    args = parser.parse_args()

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Arial", "Helvetica"],
        "figure.facecolor": BG,
        "axes.facecolor": PANEL,
    })

    cfg = load_field_config(_resolve_config(args.config))
    area = float(cfg.get("area_size_m", 10.0))
    node_pos = {int(k): tuple(v) for k, v in cfg.get("node_positions", {}).items()}
    expected_nodes = len(node_pos) or int(cfg.get("hardware", {}).get("expected_nodes", 4))

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
        while running:
            try:
                frame = engine.process_frame()
            except Exception as exc:
                frame = {
                    "error": str(exc),
                    "linked_nodes": 0,
                    "expected_nodes": expected_nodes,
                    "targets": [],
                    "target_count": 0,
                    "node_status": [],
                }
            with snap_lock:
                snapshot = frame
            time.sleep(0.1)

    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()

    print("AURA Field Live", PROCESSOR_VERSION)
    print(f"UDP :{args.port}  |  Hotspot AURA_HUB / aura2026")
    print("Walk inside the search area. Stand still for vitals. Ctrl+C to quit.\n")

    fig = plt.figure(figsize=(15.5, 9), facecolor=BG)
    try:
        fig.canvas.manager.set_window_title("AURA Field Live")  # type: ignore[union-attr]
    except Exception:
        pass

    fig.patches.append(mpatches.Circle(
        (0.04, 0.92), 0.035, transform=fig.transFigure,
        facecolor=TERTIARY, edgecolor=BORDER, linewidth=2, zorder=0, alpha=0.45,
    ))

    gs = fig.add_gridspec(
        3, 4,
        height_ratios=[0.09, 1.2, 1.0],
        width_ratios=[2.2, 0.9, 0.9, 1.1],
        hspace=0.36, wspace=0.3,
        left=0.06, right=0.97, top=0.93, bottom=0.07,
    )

    ax_title = fig.add_subplot(gs[0, :])
    ax_title.axis("off")
    ax_title.text(0.0, 0.55, "AURA Field Sensing", fontsize=18, fontweight="bold", color=FG, va="center")
    ax_title.text(0.0, 0.05, "Live ESP32 · local matplotlib", fontsize=9, color=MUTED, va="center")
    status_text = ax_title.text(
        1.0, 0.5, "Starting…", fontsize=9, color=MUTED, va="center", ha="right", family="monospace",
    )

    # Map — nodes drawn once and kept
    ax_map = fig.add_subplot(gs[1, 0])
    ax_map.set_facecolor(PANEL)
    ax_map.set_xlim(-0.5, area + 0.5)
    ax_map.set_ylim(-0.5, area + 0.5)
    ax_map.set_aspect("equal")
    ax_map.set_title("Survivor map", color=FG, fontsize=11, fontweight="bold", pad=8)
    ax_map.set_xlabel("X (m)", color=MUTED, fontsize=9)
    ax_map.set_ylabel("Y (m)", color=MUTED, fontsize=9)
    ax_map.tick_params(colors=MUTED, labelsize=8)
    ax_map.grid(True, color=GRID, alpha=0.9)
    for spine in ax_map.spines.values():
        spine.set_color(BORDER)
        spine.set_linewidth(2)

    ax_map.add_patch(mpatches.Rectangle(
        (0, 0), area, area, fill=False, edgecolor=BORDER,
        linewidth=2, linestyle=(0, (6, 4)), zorder=1,
    ))

    for nid, (nx, ny) in sorted(node_pos.items()):
        ax_map.plot(
            nx, ny, "s", color=ACCENT, markersize=13, zorder=5,
            markeredgecolor=BORDER, markeredgewidth=2,
        )
        ax_map.text(
            nx, ny - 0.55, f"N{nid}", ha="center", fontsize=9,
            color=FG, fontweight="bold", zorder=5,
        )

    trail_lines: dict[int, object] = {}
    marker_artists: dict[int, object] = {}

    # Stat panels — no axis('off') + style conflict
    ax_count = fig.add_subplot(gs[1, 1])
    _panel_ax(ax_count, "Count")
    count_num = ax_count.text(0.5, 0.58, "0", ha="center", va="center", fontsize=52, fontweight="bold", color=FG)
    ax_count.text(0.5, 0.28, "PEOPLE", ha="center", fontsize=10, color=MUTED, fontweight="bold")
    motion_badge = ax_count.text(0.5, 0.08, "CLEAR", ha="center", fontsize=11, color=QUAT, fontweight="bold")

    ax_vitals = fig.add_subplot(gs[1, 2])
    _panel_ax(ax_vitals, "Vitals")
    resp_val = ax_vitals.text(0.5, 0.58, "—", ha="center", fontsize=24, color=QUAT, fontweight="bold")
    ax_vitals.text(0.5, 0.46, "Resp BPM", ha="center", fontsize=8, color=MUTED)
    hr_val = ax_vitals.text(0.5, 0.22, "—", ha="center", fontsize=24, color=SECONDARY, fontweight="bold")
    ax_vitals.text(0.5, 0.10, "Heart BPM", ha="center", fontsize=8, color=MUTED)

    ax_nodes = fig.add_subplot(gs[1, 3])
    _panel_ax(ax_nodes, "Nodes")
    nodes_body = ax_nodes.text(
        0.05, 0.88, _format_node_lines([], expected_nodes),
        va="top", ha="left", family="monospace", fontsize=7.5, color=FG,
    )

    ax_resp = fig.add_subplot(gs[2, :2])
    resp_line, = ax_resp.plot([], [], color=QUAT, linewidth=2.5)
    _chart_ax(ax_resp, "Respiration waveform", "Time (s)")

    ax_hr = fig.add_subplot(gs[2, 2:])
    hr_line, = ax_hr.plot([], [], color=SECONDARY, linewidth=2.5)
    _chart_ax(ax_hr, "Heartbeat waveform", "Time (s)")

    def draw(_frame: int) -> list:
        with snap_lock:
            d = dict(snapshot) if snapshot else {}

        if d.get("error"):
            status_text.set_text(f"ERROR: {str(d['error'])[:72]}")
            nodes_body.set_text(f"Error:\n{str(d['error'])[:120]}")
            return []

        linked = d.get("linked_nodes", d.get("active_nodes", 0))
        sensing = d.get("sensing_nodes", 0)
        expected = d.get("expected_nodes", expected_nodes)
        pkts = d.get("total_packets", 0)
        status_text.set_text(
            f"v{PROCESSOR_VERSION}  linked {linked}/{expected}  sensing {sensing}/{expected}  "
            f"pkts {pkts}  {'MOTION' if d.get('motion_detected') else 'clear'}"
        )

        count = int(d.get("target_count", 0))
        count_num.set_text(str(count))
        if d.get("motion_detected"):
            motion_badge.set_text("MOTION")
            motion_badge.set_color(SECONDARY)
        else:
            motion_badge.set_text("CLEAR")
            motion_badge.set_color(QUAT)

        rb = float(d.get("respiration_bpm") or 0)
        hb = float(d.get("heartbeat_bpm") or 0)
        resp_val.set_text(f"{rb:.0f}" if rb and count > 0 else "—")
        hr_val.set_text(f"{hb:.0f}" if hb and count > 0 else "—")

        nodes_body.set_text(_format_node_lines(d.get("node_status", []), expected))

        tracked = d.get("targets", [])
        seen: set[int] = set()
        for t in tracked:
            tid = int(t["id"])
            seen.add(tid)
            color = PERSON_COLORS[(tid - 1) % len(PERSON_COLORS)]
            traj = t.get("trajectory", [])
            if len(traj) > 1:
                xs, ys = zip(*traj)
                if tid not in trail_lines:
                    (trail_lines[tid],) = ax_map.plot(
                        xs, ys, "-", color=color, alpha=0.55, linewidth=2.5, zorder=2,
                    )
                else:
                    trail_lines[tid].set_data(xs, ys)
            sym = "o" if t.get("is_moving") else "^"
            ms = 14 if t.get("is_moving") else 12
            if tid not in marker_artists:
                (marker_artists[tid],) = ax_map.plot(
                    [t["x_m"]], [t["y_m"]], sym, color=color, markersize=ms, zorder=6,
                    markeredgecolor=BORDER, markeredgewidth=1.5,
                )
            else:
                marker_artists[tid].set_data([t["x_m"]], [t["y_m"]])
                marker_artists[tid].set_marker(sym)
                marker_artists[tid].set_markersize(ms)

        for tid in list(trail_lines):
            if tid not in seen:
                trail_lines[tid].remove()
                del trail_lines[tid]
                if tid in marker_artists:
                    marker_artists[tid].remove()
                    del marker_artists[tid]

        fs = 20.0
        rw = d.get("respiration_waveform") or []
        hw = d.get("heartbeat_waveform") or []
        if count > 0 and len(rw):
            tx = np.linspace(0, len(rw) / fs, len(rw))
            resp_line.set_data(tx, rw)
            ax_resp.relim()
            ax_resp.autoscale_view(scalex=True, scaley=True)
        else:
            resp_line.set_data([], [])
        if count > 0 and len(hw):
            tx = np.linspace(0, len(hw) / fs, len(hw))
            hr_line.set_data(tx, hw)
            ax_hr.relim()
            ax_hr.autoscale_view(scalex=True, scaley=True)
        else:
            hr_line.set_data([], [])

        return list(trail_lines.values()) + list(marker_artists.values())

    interval_ms = int(1000 / max(args.fps, 4))
    _ani = animation.FuncAnimation(fig, draw, interval=interval_ms, blit=False, cache_frame_data=False)

    try:
        plt.show()
    except KeyboardInterrupt:
        pass
    finally:
        running = False
        worker_thread.join(timeout=1.0)
        engine.stop()


if __name__ == "__main__":
    main()
