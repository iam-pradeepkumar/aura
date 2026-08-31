"""Find WiMANS act_*.npy amplitude files on disk."""

from __future__ import annotations

from pathlib import Path


def index_amp_files(amp_dir: Path) -> dict[str, Path]:
    """Map label stem (e.g. act_100_5) -> .npy path, searching recursively."""
    amp_dir = amp_dir.expanduser().resolve()
    if not amp_dir.is_dir():
        return {}
    index: dict[str, Path] = {}
    for f in amp_dir.rglob("act_*.npy"):
        index[f.stem.lower()] = f
    return index


def resolve_amp_dir(path: str | Path) -> tuple[Path | None, dict[str, Path]]:
    """
    Resolve user path to the folder containing act_*.npy files.
    Accepts wifi_csi/, amp/, or the dataset root.
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return None, {}

    # Direct hit
    idx = index_amp_files(p)
    if idx:
        return p, idx

    # Common WiMANS layouts
    for candidate in (
        p / "wifi_csi" / "amp",
        p / "dataset" / "wifi_csi" / "amp",
        p / "amp",
        p / "WiMANS" / "dataset" / "wifi_csi" / "amp",
    ):
        if candidate.is_dir():
            idx = index_amp_files(candidate)
            if idx:
                return candidate, idx

    # Any act_*.npy under this tree
    hits = list(p.rglob("act_*.npy"))
    if hits:
        folder = hits[0].parent
        return folder, index_amp_files(folder)

    return p if p.is_dir() else None, {}
