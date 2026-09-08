#!/usr/bin/env python3
"""
AURA Field Live — local matplotlib dashboard for ESP32 CSI sensing.

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

# Hand-Drawn sketch palette
BG = "#fdfbf7"
FG = "#2d2d2d"
MUTED = "#6b7280"
BORDER = "#2d2d2d"
ACCENT = "#ff4d4d"
SECONDARY = "#2d5da1"
TERTIARY = "#fff9c4"
QUAT = "#15803d"
PANEL = "#ffffff"
GRID = "#e5e0d8"
PERSON_COLORS = [ACCENT, SECONDARY, "#f59e0b", QUAT, "#7c3aed", "#ea580c", "#0891b2", "#be185d"]


def _panel_ax(ax, title: str = "") -> None:
    ax.set_facecolor(PANEL)
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color(BORDER)
        spine.set_linewidth(2)
    if title:
        ax.set_title(title, color=FG, fontsize=12, fontweight="bold", pad=10)


def _chart_ax(ax, title: str, xlabel: str = "") -> None:
    ax.set_facecolor(PANEL)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color(BORDER)
        spine.set_linewidth(2)
    ax.tick_params(colors=FG, labelsize=9)
    ax.set_title(title, color=FG, fontsize=12, fontweight="bold", pad=10)
    ax.grid(True, color=GRID, alpha=0.85, linewidth=1)
    if xlabel:
        ax.set_xlabel(xlabel, color=MUTED, fontsize=10)


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
        st = str(n.get("status", "?"))[:14]
        hz = float(n.get("packet_rate_hz") or 0)
        mot = "●" if n.get("motion") else "○"
        cnt = n.get("count", "")
        cnt_s = f" c={cnt}" if cnt not in ("", None) else ""
        sc = n.get("motion_score", "")
        sc_s = f" m={sc}" if sc != "" else ""
        lines.append(f"N{nid} {st:14} {hz:4.0f}Hz {mot}{cnt_s}{sc_s}")
    return "\n".join(lines)


def _normalize_wave(arr: list | np.ndarray) -> np.ndarray:
    a = np.asarray(arr, dtype=float)
    if a.size < 4:
        return a
    std = float(np.std(a))
    if std < 1e-9:
        return a - float(np.mean(a))
    return (a - float(np.mean(a))) / std


def _format_count(n: int, cap: int) -> str:
    if n >= cap:
        return f"{cap}+"
    return str(n)


def main() -> None:
    parser = argparse.ArgumentParser(description="AURA local field live sensing (matplotlib)")
    parser.add_argument("--port", type=int, default=DEFAULT_UDP_PORT)
    parser.add_argument("--config", default="simulation/config.yaml")
    parser.add_argument("--fps", type=float, default=None, help="Display refresh rate")
    args = parser.parse_args()

    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Patrick Hand", "Kalam", "Comic Sans MS", "DejaVu Sans"],
        "figure.facecolor": BG,
        "axes.facecolor": PANEL,
        "axes.edgecolor": BORDER,
        "axes.linewidth": 2,
        "text.color": FG,
        "axes.labelcolor": FG,
        "xtick.color": FG,
        "ytick.color": FG,
    })

    cfg = load_field_config(_resolve_config(args.config))
    hw = cfg.get("hardware", {})
    area = float(cfg.get("area_size_m", 10.0))
    max_people = int(hw.get("max_people", cfg.get("max_people", 24)))
    indoor = bool(hw.get("indoor_mode", False))
    node_pos = {int(k): tuple(v) for k, v in cfg.get("node_positions", {}).items()}
    expected_nodes = len(node_pos) or int(hw.get("expected_nodes", 4))
    display_fps = float(args.fps or hw.get("display_fps", 20))
    worker_ms = float(hw.get("worker_interval_ms", 40)) / 1000.0

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
            time.sleep(worker_ms)

    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()

    mode_label = "INDOOR" if indoor else "FIELD"
    print(f"AURA Field Live {PROCESSOR_VERSION} [{mode_label}]")
    print(f"UDP :{args.port}  |  Hotspot AURA_HUB / aura2026  |  max {max_people} people")
    print("Stand in empty room ~4s for calibration, then walk the search area. Ctrl+C to quit.\n")

    fig = plt.figure(figsize=(16, 10), facecolor=BG, constrained_layout=False)
    try:
        fig.canvas.manager.set_window_title("AURA Field Live")  # type: ignore[union-attr]
    except Exception:
        pass

    fig.patches.append(mpatches.FancyBboxPatch(
        (0.015, 0.015), 0.97, 0.97, transform=fig.transFigure,
        boxstyle="round,pad=0.01,rounding_size=0.02",
        facecolor="none", edgecolor=BORDER, linewidth=2, linestyle=(0, (8, 5)), zorder=-1, alpha=0.3,
    ))

    gs = fig.add_gridspec(
        3, 4,
        height_ratios=[0.11, 1.45, 1.05],
        width_ratios=[2.5, 1.0, 1.0, 1.15],
        hspace=0.32, wspace=0.28,
        left=0.045, right=0.985, top=0.94, bottom=0.07,
    )

    # Header
    ax_title = fig.add_subplot(gs[0, :])
    ax_title.axis("off")
    ax_title.text(0.0, 0.62, "AURA Field Sensing", fontsize=20, fontweight="bold", color=FG, va="center")
    badge = f" {mode_label} " if indoor else " FIELD "
    ax_title.text(0.0, 0.08, f"✎ live rescue view ·{badge}· max {max_people}", fontsize=10, color=MUTED, va="center")
    status_text = ax_title.text(
        1.0, 0.5, "Starting…", fontsize=10, color=FG, va="center", ha="right", family="monospace",
    )

    # Survivor map
    ax_map = fig.add_subplot(gs[1, 0])
    ax_map.set_facecolor(PANEL)
    ax_map.set_xlim(-0.4, area + 0.4)
    ax_map.set_ylim(-0.4, area + 0.4)
    ax_map.set_aspect("equal")
    ax_map.set_title("Survivor map", color=FG, fontsize=12, fontweight="bold", pad=10)
    ax_map.set_xlabel("X (m)", color=MUTED, fontsize=10)
    ax_map.set_ylabel("Y (m)", color=MUTED, fontsize=10)
    ax_map.tick_params(colors=FG, labelsize=9)
    ax_map.grid(True, color=GRID, alpha=0.85)
    for spine in ax_map.spines.values():
        spine.set_color(BORDER)
        spine.set_linewidth(2)
    ax_map.add_patch(mpatches.Rectangle(
        (0, 0), area, area, fill=False, edgecolor=BORDER,
        linewidth=2, linestyle=(0, (6, 4)), zorder=1,
    ))
    for nid, (nx, ny) in sorted(node_pos.items()):
        ax_map.plot(nx, ny, "s", color=ACCENT, markersize=12, zorder=5, markeredgecolor=BORDER, markeredgewidth=2)
        ax_map.text(nx, ny - 0.45, f"N{nid}", ha="center", fontsize=9, color=FG, fontweight="bold", zorder=5)

    trail_lines: dict[int, object] = {}
    marker_artists: dict[int, object] = {}
    label_artists: dict[int, object] = {}

    # Count panel
    ax_count = fig.add_subplot(gs[1, 1])
    _panel_ax(ax_count, "Count")
    count_num = ax_count.text(0.5, 0.56, "0", ha="center", va="center", fontsize=48, fontweight="bold", color=FG)
    ax_count.text(0.5, 0.30, "PEOPLE", ha="center", fontsize=11, color=MUTED, fontweight="bold")
    motion_badge = ax_count.text(0.5, 0.10, "CLEAR", ha="center", fontsize=12, color=QUAT, fontweight="bold")
    tracked_hint = ax_count.text(0.5, 0.02, "", ha="center", fontsize=8, color=MUTED)

    # Vitals panel
    ax_vitals = fig.add_subplot(gs[1, 2])
    _panel_ax(ax_vitals, "Vitals")
    resp_val = ax_vitals.text(0.5, 0.60, "—", ha="center", fontsize=26, color=QUAT, fontweight="bold")
    ax_vitals.text(0.5, 0.47, "Resp BPM", ha="center", fontsize=9, color=MUTED)
    hr_val = ax_vitals.text(0.5, 0.24, "—", ha="center", fontsize=26, color=SECONDARY, fontweight="bold")
    ax_vitals.text(0.5, 0.11, "Heart BPM", ha="center", fontsize=9, color=MUTED)

    # Nodes panel
    ax_nodes = fig.add_subplot(gs[1, 3])
    _panel_ax(ax_nodes, "Nodes")
    nodes_body = ax_nodes.text(
        0.04, 0.92, _format_node_lines([], expected_nodes),
        va="top", ha="left", family="monospace", fontsize=8.5, color=FG, linespacing=1.35,
    )

    # Waveforms
    ax_resp = fig.add_subplot(gs[2, :2])
    resp_line, = ax_resp.plot([], [], color=QUAT, linewidth=2.2)
    _chart_ax(ax_resp, "Respiration waveform", "Time (s)")
    ax_resp.set_ylim(-2.5, 2.5)

    ax_hr = fig.add_subplot(gs[2, 2:])
    hr_line, = ax_hr.plot([], [], color=SECONDARY, linewidth=2.2)
    _chart_ax(ax_hr, "Heartbeat waveform", "Time (s)")
    ax_hr.set_ylim(-2.5, 2.5)

    def draw(_frame: int) -> list:
        with snap_lock:
            d = dict(snapshot) if snapshot else {}

        if d.get("error"):
            status_text.set_text(f"ERROR: {str(d['error'])[:80]}")
            nodes_body.set_text(f"Error:\n{str(d['error'])[:140]}")
            return []

        cal_pct = int(float(d.get("calibration_progress", 0)) * 100)
        cal_ok = d.get("calibration_ready", False)
        conf_pct = int(float(d.get("sensing_confidence", 0)) * 100)
        linked = d.get("linked_nodes", d.get("active_nodes", 0))
        sensing = d.get("sensing_nodes", 0)
        expected = d.get("expected_nodes", expected_nodes)
        pkts = d.get("total_packets", 0)
        motion = bool(d.get("motion_detected"))
        motion_nodes = d.get("motion_nodes", 0)

        status_text.set_text(
            f"v{PROCESSOR_VERSION}  linked {linked}/{expected}  sensing {sensing}/{expected}  "
            f"conf {conf_pct}%  {'CAL OK' if cal_ok else f'cal {cal_pct}%'}  "
            f"motion {motion_nodes}n  pkts {pkts}  {'MOTION' if motion else 'clear'}"
        )

        count = int(d.get("target_count", 0))
        tracked = d.get("targets", [])
        count_num.set_text(_format_count(count, max_people))
        count_num.set_fontsize(40 if count >= 10 else 48)
        tracked_hint.set_text(f"{len(tracked)} tracked" if count > 0 else "")

        if motion:
            motion_badge.set_text("MOTION")
            motion_badge.set_color(SECONDARY)
        else:
            motion_badge.set_text("CLEAR")
            motion_badge.set_color(QUAT)

        show_vitals = count > 0 or motion
        rb = float(d.get("respiration_bpm") or 0)
        hb = float(d.get("heartbeat_bpm") or 0)
        resp_val.set_text(f"{rb:.0f}" if rb and show_vitals else "—")
        hr_val.set_text(f"{hb:.0f}" if hb and show_vitals else "—")

        nodes_body.set_text(_format_node_lines(d.get("node_status", []), expected))

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
                        xs, ys, "-", color=color, alpha=0.5, linewidth=2.2, zorder=2,
                    )
                else:
                    trail_lines[tid].set_data(xs, ys)
            sym = "o" if t.get("is_moving") else "^"
            ms = 13 if t.get("is_moving") else 11
            if tid not in marker_artists:
                (marker_artists[tid],) = ax_map.plot(
                    [t["x_m"]], [t["y_m"]], sym, color=color, markersize=ms, zorder=6,
                    markeredgecolor=BORDER, markeredgewidth=1.5,
                )
            else:
                marker_artists[tid].set_data([t["x_m"]], [t["y_m"]])
                marker_artists[tid].set_marker(sym)
                marker_artists[tid].set_markersize(ms)
            if tid not in label_artists:
                label_artists[tid] = ax_map.text(
                    t["x_m"] + 0.25, t["y_m"] + 0.25, f"P{tid}",
                    fontsize=8, color=color, fontweight="bold", zorder=7,
                )
            else:
                label_artists[tid].set_position((t["x_m"] + 0.25, t["y_m"] + 0.25))

        for tid in list(trail_lines):
            if tid not in seen:
                trail_lines[tid].remove()
                del trail_lines[tid]
                if tid in marker_artists:
                    marker_artists[tid].remove()
                    del marker_artists[tid]
                if tid in label_artists:
                    label_artists[tid].remove()
                    del label_artists[tid]

        fs = 20.0
        rw = d.get("respiration_waveform") or []
        hw = d.get("heartbeat_waveform") or []
        if show_vitals and len(rw) >= 4:
            arr = _normalize_wave(rw)
            tx = np.linspace(0, len(arr) / fs, len(arr))
            resp_line.set_data(tx, arr)
            ax_resp.set_xlim(0, max(tx[-1], 0.5))
        else:
            resp_line.set_data([], [])
            ax_resp.set_xlim(0, 4)
        if show_vitals and len(hw) >= 4:
            arr = _normalize_wave(hw)
            tx = np.linspace(0, len(arr) / fs, len(arr))
            hr_line.set_data(tx, arr)
            ax_hr.set_xlim(0, max(tx[-1], 0.5))
        else:
            hr_line.set_data([], [])
            ax_hr.set_xlim(0, 4)

        return list(trail_lines.values()) + list(marker_artists.values())

    interval_ms = int(1000 / max(display_fps, 8))
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
