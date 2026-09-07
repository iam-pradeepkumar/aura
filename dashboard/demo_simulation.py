"""Generate a self-contained WiMANS-style demo session for the simulation lab."""

from __future__ import annotations

import uuid
from pathlib import Path

import cv2
import numpy as np

from simulation.wimans.synthetic import synth_amplitude


def _write_demo_video(path: Path, frames: int, fps: float = 30.0) -> tuple[float, int]:
    """Simple scene video (top-down room sketch) for sync."""
    w, h = 640, 360
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(path), fourcc, fps, (w, h))
    duration = frames / fps
    for i in range(frames):
        t = i / max(frames - 1, 1)
        img = np.full((h, w, 3), 245, dtype=np.uint8)
        # Room border
        cv2.rectangle(img, (40, 30), (w - 40, h - 30), (45, 45, 45), 2)
        # Moving person dot
        px = int(80 + t * (w - 200))
        py = int(h / 2 + 40 * np.sin(t * 6 * np.pi))
        cv2.circle(img, (px, py), 18, (45, 93, 161), -1)
        cv2.putText(img, "AURA demo scene", (50, 55), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (30, 30, 30), 2)
        writer.write(img)
    writer.release()
    return duration, frames


def generate_demo_triple(out_dir: Path, stem: str = "act_demo_1") -> dict[str, Path]:
    """Create .mp4 + .mat + .npy triple compatible with the upload pipeline."""
    try:
        import scipy.io
    except ImportError as exc:
        raise RuntimeError("scipy required for demo generation") from exc

    out_dir.mkdir(parents=True, exist_ok=True)
    frames = 900
    n_sc = 30
    fps = 30.0
    amp = synth_amplitude(
        n_users=1,
        locations=["c"],
        activities=["walk"],
        seed=42,
        frames=frames,
        n_sc=n_sc,
    )
    # Complex CSI from amplitude + synthetic phase
    phase = np.cumsum(np.random.default_rng(7).normal(0, 0.05, amp.shape), axis=0)
    csi = amp * np.exp(1j * phase)
    timestamps_ms = (np.arange(frames) * (1000.0 / fps)).astype(np.float64)

    video_path = out_dir / f"{stem}.mp4"
    mat_path = out_dir / f"{stem}.mat"
    npy_path = out_dir / f"{stem}.npy"

    duration, n_frames = _write_demo_video(video_path, frames, fps)
    np.save(npy_path, amp.astype(np.float32))
    scipy.io.savemat(
        mat_path,
        {
            "csi": csi.astype(np.complex64),
            "amplitude": amp.astype(np.float32),
            "timestamp_ms": timestamps_ms,
            "sample_rate_hz": float(fps),
        },
    )
    return {
        "video": video_path,
        "mat": mat_path,
        "npy": npy_path,
        "stem": stem,
        "fps": fps,
        "duration_sec": duration,
        "n_frames": n_frames,
    }
