"""Use bundled WiMANS act_105_48 dataset for the simulation lab demo."""

from __future__ import annotations

import shutil
from pathlib import Path

DEMO_DATA_DIR = Path(__file__).resolve().parent / "demo_data"
STEM = "act_105_48"


def bundled_demo_paths() -> dict[str, Path]:
    """Return paths to the committed demo triple (video + .mat + .npy)."""
    video = DEMO_DATA_DIR / f"{STEM}.mp4"
    mat = DEMO_DATA_DIR / f"{STEM}.mat"
    npy = DEMO_DATA_DIR / f"{STEM}.npy"
    missing = [p.name for p in (video, mat, npy) if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            f"Demo dataset incomplete in {DEMO_DATA_DIR}: missing {', '.join(missing)}"
        )
    return {"video": video, "mat": mat, "npy": npy, "stem": STEM}


def copy_demo_triple(out_dir: Path) -> dict[str, Path]:
    """Copy bundled WiMANS files into a session upload directory."""
    out_dir.mkdir(parents=True, exist_ok=True)
    src = bundled_demo_paths()
    video_path = out_dir / "video.mp4"
    mat_path = out_dir / f"{STEM}.mat"
    npy_path = out_dir / f"{STEM}.npy"
    shutil.copy2(src["video"], video_path)
    shutil.copy2(src["mat"], mat_path)
    shutil.copy2(src["npy"], npy_path)
    return {
        "video": video_path,
        "mat": mat_path,
        "npy": npy_path,
        "stem": STEM,
    }
