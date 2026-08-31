#!/usr/bin/env python3
"""
AURA Live Simulation Viewer

Sync video (.mp4) with CSI dataset (.npy, .mat, .csv, .bin).
Displays: survivor count, XY localization, trajectories, vital signs, motion.

Usage:
  python run_simulation.py --video rescue.mp4 --csi session.npy
  python run_simulation.py --video rescue.mp4 --csi session.mat --fs 1000
  python run_simulation.py --video rescue.mp4 --csi session.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).parent))

from aura_processor import load_csi, AURAPipeline
from aura_processor.multitarget import trim_csi_to_video


def load_config(path: str | None) -> dict:
    defaults = {
        "area_size_m": 10.0,
        "motion_threshold": 0.02,
        "node_positions": {
            1: [0.0, 0.0],
            2: [10.0, 0.0],
            3: [5.0, 8.7],
            4: [0.0, 10.0],
        },
    }
    if path and Path(path).exists():
        with open(path) as f:
            user = yaml.safe_load(f) or {}
        defaults.update(user)
    return defaults


def align_results_to_video(
    results: list,
    video_duration_sec: float,
    n_frames: int,
) -> list:
    if not results:
        return [None] * n_frames
    t_max = max(r.timestamp_sec for r in results)
    t_scale = video_duration_sec / max(t_max, 1e-3)
    aligned = []
    for fi in range(n_frames):
        t_video = (fi / max(n_frames - 1, 1)) * video_duration_sec
        t_csi = t_video / t_scale if t_scale > 0 else t_video
        best = min(results, key=lambda r: abs(r.timestamp_sec - t_csi))
        aligned.append(best)
    return aligned


def resolve_paths(video: str, csi: str | None, data_dir: str | None) -> tuple[Path, Path]:
    """Resolve --video + --csi, or auto-find matching .npy/.mat in --data-dir."""
    if data_dir:
        d = Path(data_dir)
        videos = list(d.glob("*.mp4"))
        if not videos:
            sys.exit(f"No .mp4 found in {d}")
        video_path = videos[0]
        stem = video_path.stem
        for ext in (".npy", ".mat", ".npz", ".csv", ".bin"):
            candidate = d / f"{stem}{ext}"
            if candidate.exists():
                return video_path, candidate
        # any csi file in folder
        for ext in (".npy", ".mat", ".npz", ".csv", ".bin"):
            files = list(d.glob(f"*{ext}"))
            if files:
                return video_path, files[0]
        sys.exit(f"No CSI file (.npy/.mat/.csv) found in {d}")
    if not video or not csi:
        sys.exit("Provide --video and --csi, or use --data-dir with your .mp4 + .npy/.mat")
    return Path(video), Path(csi)


def main():
    parser = argparse.ArgumentParser(description="AURA video + CSI live viewer")
    parser.add_argument("--video", help="Scene video (.mp4)")
    parser.add_argument("--csi", help="CSI dataset (.npy, .mat, .npz, .csv, .bin)")
    parser.add_argument("--data-dir", help="Folder containing matching .mp4 and .npy/.mat")
    parser.add_argument("--fs", type=float, default=None, help="CSI sample rate Hz (for .npy/.mat without timestamps)")
    parser.add_argument("--config", default="config.yaml", help="Node layout config")
    parser.add_argument("--save", default=None, help="Save animation to MP4/GIF")
    args = parser.parse_args()

    video_path, csi_path = resolve_paths(args.video, args.csi, args.data_dir)
    if not video_path.exists():
        sys.exit(f"Video not found: {video_path}")
    if not csi_path.exists():
        sys.exit(f"CSI not found: {csi_path}")

    print(f"Video: {video_path}")
    print(f"CSI:   {csi_path}")

    cfg = load_config(args.config)
    node_pos = {int(k): tuple(v) for k, v in cfg.get("node_positions", {}).items()}

    data = load_csi(csi_path, sample_rate_hz=args.fs)
    print(f"Loaded {len(data['csi'])} CSI frames, {data['csi'].shape[1]} subcarriers, fs={data['sample_rate_hz']:.1f} Hz")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        sys.exit(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    n_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = n_frames / fps

    pipeline = AURAPipeline(
        fs_hz=data["sample_rate_hz"],
        area_size_m=cfg.get("area_size_m", 10.0),
        motion_threshold=cfg.get("motion_threshold", 0.02),
        node_positions=node_pos,
    )
    results = pipeline.process_session(data["csi"], data["timestamps_ms"])
    aligned = align_results_to_video(results, duration, n_frames)

    fig = plt.figure(figsize=(14, 9))
    fig.suptitle("AURA — Adaptive Urban Rescue Array (CSI-Only Sensing)", fontsize=14, fontweight="bold")
    gs = fig.add_gridspec(3, 3, hspace=0.35, wspace=0.3)

    ax_video = fig.add_subplot(gs[0, :2])
    ax_map = fig.add_subplot(gs[1:, :2])
    ax_count = fig.add_subplot(gs[0, 2])
    ax_resp = fig.add_subplot(gs[1, 2])
    ax_hr = fig.add_subplot(gs[2, 2])

    area = cfg.get("area_size_m", 10.0)
    ax_map.set_xlim(0, area)
    ax_map.set_ylim(0, area)
    ax_map.set_aspect("equal")
    ax_map.set_xlabel("X (m)")
    ax_map.set_ylabel("Y (m)")
    ax_map.set_title("Survivor Localization (CSI)")
    ax_map.grid(True, alpha=0.3)

    for nid, (nx, ny) in node_pos.items():
        ax_map.plot(nx, ny, "s", color="#2563eb", markersize=10)
    ax_map.plot([], [], "s", color="#2563eb", label="ESP32 Node")

    scatter_mov = ax_map.scatter([], [], c="#ef4444", s=120, marker="o", zorder=5)
    scatter_static = ax_map.scatter([], [], c="#f59e0b", s=120, marker="^", zorder=5)

    ax_count.set_title("People Count")
    count_text = ax_count.text(0.5, 0.55, "0", ha="center", va="center", fontsize=48, fontweight="bold")
    motion_text = ax_count.text(0.5, 0.2, "", ha="center", va="center", fontsize=11)
    ax_count.set_xlim(0, 1)
    ax_count.set_ylim(0, 1)
    ax_count.axis("off")

    ax_resp.set_title("Respiration (~11/min ref)")
    ax_hr.set_title("Heartbeat (~65/min ref)")
    resp_line, = ax_resp.plot([], [], color="#10b981")
    hr_line, = ax_hr.plot([], [], color="#8b5cf6")
    ax_resp.set_xlabel("Time (s)")
    ax_hr.set_xlabel("Time (s)")

    status_text = fig.text(0.02, 0.02, "", fontsize=9, family="monospace")
    drawn_trajs: list = []

    def update(frame_idx):
        for ln in drawn_trajs:
            ln.remove()
        drawn_trajs.clear()

        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            ax_video.imshow(frame_rgb)
            ax_video.set_title(f"Scene Video — frame {frame_idx + 1}/{n_frames} ({frame_idx / fps:.2f}s)")
            ax_video.axis("off")

        res = aligned[frame_idx] if frame_idx < len(aligned) else None
        if res is None:
            return []

        count_text.set_text(str(res.target_count))
        motion_text.set_text("MOTION" if res.motion_detected else "STATIC / VITALS")
        motion_text.set_color("#ef4444" if res.motion_detected else "#10b981")

        mov_x, mov_y, stat_x, stat_y = [], [], [], []
        for t in res.targets:
            if t.is_moving:
                mov_x.append(t.x_m)
                mov_y.append(t.y_m)
            else:
                stat_x.append(t.x_m)
                stat_y.append(t.y_m)
            if len(t.trajectory) > 1:
                tx, ty = zip(*t.trajectory[-30:])
                ln, = ax_map.plot(tx, ty, "-", alpha=0.4, linewidth=1, color="#94a3b8")
                drawn_trajs.append(ln)

        scatter_mov.set_offsets(np.c_[mov_x, mov_y] if mov_x else np.empty((0, 2)))
        scatter_static.set_offsets(np.c_[stat_x, stat_y] if stat_x else np.empty((0, 2)))

        t_axis = np.linspace(0, res.timestamp_sec, len(res.respiration_waveform or []))
        if res.respiration_waveform is not None and len(t_axis):
            resp_line.set_data(t_axis, res.respiration_waveform)
            ax_resp.set_xlim(0, max(res.timestamp_sec, 0.5))
            ax_resp.set_ylim(res.respiration_waveform.min() - 0.1, res.respiration_waveform.max() + 0.1)
            ax_resp.set_ylabel(f"{res.respiration_bpm:.1f} BPM")

        if res.heartbeat_waveform is not None and len(t_axis):
            hr_line.set_data(t_axis, res.heartbeat_waveform)
            ax_hr.set_xlim(0, max(res.timestamp_sec, 0.5))
            ax_hr.set_ylim(res.heartbeat_waveform.min() - 0.1, res.heartbeat_waveform.max() + 0.1)
            ax_hr.set_ylabel(f"{res.heartbeat_bpm:.1f} BPM")

        status_text.set_text(
            f"CSI: {csi_path.name} | fs={data['sample_rate_hz']:.1f}Hz | "
            f"Resp={res.respiration_bpm:.1f} BPM | HR={res.heartbeat_bpm:.1f} BPM | "
            f"Energy={res.motion_energy:.4f}"
        )
        return [scatter_mov, scatter_static, count_text, motion_text, resp_line, hr_line, status_text]

    anim = animation.FuncAnimation(fig, update, frames=n_frames, interval=1000 / fps, blit=False)

    if args.save:
        print(f"Saving to {args.save}...")
        if args.save.endswith(".gif"):
            anim.save(args.save, writer="pillow", fps=fps)
        else:
            anim.save(args.save, writer="ffmpeg", fps=fps)
    else:
        plt.show()

    cap.release()


if __name__ == "__main__":
    main()
