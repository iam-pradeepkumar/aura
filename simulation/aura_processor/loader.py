"""CSI data loaders — CSV, binary, .npy, .mat (Intel/csiread/WiDFS formats)."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

AURA_MAGIC = 0x41555241
HEADER_FMT = "<IBBBBIIbBHHI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)


def load_csi(path: str | Path, sample_rate_hz: float | None = None) -> dict:
    """Auto-detect format from extension and load CSI session."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".bin":
        return load_csi_binary(path)
    if ext == ".csv":
        return load_csi_csv(path)
    if ext == ".npy":
        return load_csi_npy(path, sample_rate_hz=sample_rate_hz)
    if ext == ".npz":
        return load_csi_npz(path, sample_rate_hz=sample_rate_hz)
    if ext == ".mat":
        return load_csi_mat(path, sample_rate_hz=sample_rate_hz)
    raise ValueError(f"Unsupported CSI format: {ext}. Use .csv, .bin, .npy, .npz, or .mat")


def iq_to_complex(iq: np.ndarray) -> np.ndarray:
    """Convert interleaved int8 I/Q (Imag, Real per Espressif) to complex."""
    if iq.ndim == 1:
        imag = iq[0::2].astype(np.float32)
        real = iq[1::2].astype(np.float32)
        return real + 1j * imag
    raise ValueError("Expected 1-D interleaved I/Q buffer")


def _to_complex_2d(arr: np.ndarray) -> np.ndarray:
    """Normalize various CSI array layouts to (frames, subcarriers) complex."""
    arr = np.asarray(arr)

    if np.iscomplexobj(arr):
        out = arr
    elif arr.ndim == 4:
        # (packets, tones, nrx, ntx) — Intel/Atheros/csiread container
        out = arr[:, :, 0, 0]
        if not np.iscomplexobj(out):
            out = out.astype(np.complex64)
    elif arr.ndim == 3:
        if arr.shape[-1] == 2:
            # (T, N, 2) real/imag
            out = arr[..., 0] + 1j * arr[..., 1]
        elif arr.shape[1] == 2:
            # (T, 2, N)
            out = arr[:, 0, :] + 1j * arr[:, 1, :]
        else:
            # (T, nrx, tones) — take first antenna
            out = arr[:, 0, :].astype(np.complex64)
    elif arr.ndim == 2:
        if arr.shape[1] % 2 == 0 and not np.iscomplexobj(arr):
            # Possibly interleaved I/Q columns
            try:
                out = iq_to_complex(arr[0])  # test one row
                out = np.stack([iq_to_complex(row) for row in arr])
            except Exception:
                out = arr.astype(np.complex64)
        else:
            out = arr.astype(np.complex64)
    else:
        raise ValueError(f"Cannot interpret CSI shape {arr.shape}")

    if out.ndim != 2:
        out = out.reshape(out.shape[0], -1)
    return out.astype(np.complex64)


def _extract_timestamps(
    meta: dict,
    n_frames: int,
    sample_rate_hz: float | None,
) -> tuple[np.ndarray, float]:
    """Find timestamps in metadata dict or synthesize from sample rate."""
    for key in ("timestamp_ms", "timestamps_ms", "timestamp", "timestamps", "ts", "time"):
        if key in meta:
            ts = np.asarray(meta[key], dtype=np.float64).ravel()
            if key in ("timestamp", "timestamps", "ts", "time") and ts.max() < 1000:
                ts = ts * 1000.0
            if len(ts) == n_frames:
                return ts, _estimate_fs(ts)

    fs = sample_rate_hz or float(meta.get("sample_rate_hz", meta.get("fs", 20.0)))
    ts = np.arange(n_frames, dtype=np.float64) * (1000.0 / fs)
    return ts, fs


def _extract_node_ids(meta: dict, n_frames: int) -> np.ndarray:
    for key in ("node_id", "node_ids", "rx_id", "antenna"):
        if key in meta:
            ids = np.asarray(meta[key], dtype=np.int32).ravel()
            if len(ids) == n_frames:
                return ids
            if len(ids) == 1:
                return np.full(n_frames, ids[0], dtype=np.int32)
    return np.zeros(n_frames, dtype=np.int32)


def load_csi_npy(path: str | Path, sample_rate_hz: float | None = None) -> dict:
    """
    Load .npy CSI array.

    Supported shapes:
      - (frames, subcarriers) complex
      - (frames, subcarriers, 2) or (frames, 2, subcarriers) real/imag
      - (frames, tones, nrx, ntx) Intel/csiread style

    Optional companion: same basename + _meta.npy with timestamps/node_id keys.
    """
    path = Path(path)
    raw = np.load(path, allow_pickle=True)

    meta: dict = {}
    if raw.dtype == object:
        raw = raw.item()
        if isinstance(raw, dict):
            meta = raw
            csi_key = next((k for k in ("csi", "CSI", "data", "H") if k in meta), None)
            if csi_key is None:
                raise ValueError(f".npy dict must contain 'csi' key. Found: {list(meta.keys())}")
            arr = meta[csi_key]
        else:
            arr = raw
    else:
        arr = raw
        meta_path = path.with_name(path.stem + "_meta.npy")
        if meta_path.exists():
            meta_obj = np.load(meta_path, allow_pickle=True)
            meta = meta_obj.item() if meta_obj.dtype == object else {"meta": meta_obj}

    csi = _to_complex_2d(arr)
    timestamps, fs = _extract_timestamps(meta, len(csi), sample_rate_hz)
    node_ids = _extract_node_ids(meta, len(csi))

    return {
        "csi": csi,
        "timestamps_ms": timestamps,
        "node_ids": node_ids,
        "sample_rate_hz": fs,
        "source": str(path),
    }


def load_csi_npz(path: str | Path, sample_rate_hz: float | None = None) -> dict:
    """Load .npz with keys like csi, timestamp_ms, node_id."""
    path = Path(path)
    data = np.load(path, allow_pickle=True)
    meta = {k: data[k] for k in data.files}
    csi_key = next((k for k in ("csi", "CSI", "data", "H") if k in meta), None)
    if csi_key is None:
        raise ValueError(f".npz must contain 'csi' array. Found: {list(meta.keys())}")
    csi = _to_complex_2d(meta[csi_key])
    timestamps, fs = _extract_timestamps(meta, len(csi), sample_rate_hz)
    node_ids = _extract_node_ids(meta, len(csi))
    return {
        "csi": csi,
        "timestamps_ms": timestamps,
        "node_ids": node_ids,
        "sample_rate_hz": fs,
        "source": str(path),
    }


def load_csi_mat(path: str | Path, sample_rate_hz: float | None = None) -> dict:
    """
    Load .mat CSI (Intel 5300 / csiread / WiDFS exports).

    Tries csiread if installed; otherwise scipy.io.loadmat with common field names.
    """
    path = Path(path)

    try:
        import csiread  # type: ignore

        return _load_mat_csiread(path, sample_rate_hz)
    except ImportError:
        pass

    from scipy.io import loadmat

    mat = loadmat(path, squeeze_me=True, struct_as_record=False)
    meta = {k: v for k, v in mat.items() if not k.startswith("__")}

    csi_key = next((k for k in ("csi", "CSI", "data", "csi_data", "H", "cfm") if k in meta), None)
    if csi_key is None:
        raise ValueError(
            f"No CSI field in {path.name}. Expected one of: csi, CSI, data, csi_data. "
            f"Found: {list(meta.keys())}"
        )

    raw = meta[csi_key]

    # MATLAB cell array of per-packet CSI
    if isinstance(raw, np.ndarray) and raw.dtype == object:
        frames = []
        for cell in raw.ravel():
            frames.append(_to_complex_2d(np.asarray(cell)))
        # Pad to same subcarrier count
        max_sc = max(f.shape[-1] for f in frames)
        csi = np.stack([np.pad(f, ((0, 0), (0, max_sc - f.shape[1])), mode="edge") for f in frames])
    else:
        csi = _to_complex_2d(np.asarray(raw))

    timestamps, fs = _extract_timestamps(meta, len(csi), sample_rate_hz)
    node_ids = _extract_node_ids(meta, len(csi))

    return {
        "csi": csi,
        "timestamps_ms": timestamps,
        "node_ids": node_ids,
        "sample_rate_hz": fs,
        "source": str(path),
    }


def _load_mat_csiread(path: Path, sample_rate_hz: float | None) -> dict:
    import csiread

    reader = csiread.Intel(str(path))
    reader.read()
    csi = reader.csi
    if csi.ndim == 4:
        csi = csi[:, :, 0, 0]
    csi = _to_complex_2d(csi)

    if hasattr(reader, "timestamp") and len(reader.timestamp) == len(csi):
        ts = np.asarray(reader.timestamp, dtype=np.float64)
        if ts.max() < 1000:
            ts = ts * 1000.0
    else:
        fs = sample_rate_hz or 1000.0
        ts = np.arange(len(csi)) * (1000.0 / fs)

    fs = sample_rate_hz or _estimate_fs(ts)
    return {
        "csi": csi,
        "timestamps_ms": ts,
        "node_ids": np.zeros(len(csi), dtype=np.int32),
        "sample_rate_hz": fs,
        "source": str(path),
    }


def load_csi_csv(path: str | Path) -> dict:
    path = Path(path)
    df = pd.read_csv(path)

    if "iq" in df.columns:
        csi = np.stack([iq_to_complex(np.array(eval(s), dtype=np.int8)) for s in df["iq"]])
    else:
        iq_cols = [c for c in df.columns if c.endswith("_i")]
        sc_indices = sorted(int(c.split("_")[0][2:]) for c in iq_cols)
        rows = []
        for _, row in df.iterrows():
            vals = []
            for sc in sc_indices:
                vals.extend([row[f"sc{sc}_i"], row[f"sc{sc}_q"]])
            rows.append(iq_to_complex(np.array(vals, dtype=np.int8)))
        csi = np.stack(rows)

    timestamps = df["timestamp_ms"].to_numpy(dtype=np.float64)
    if "node_id" in df.columns:
        node_ids = df["node_id"].to_numpy(dtype=np.int32)
    else:
        node_ids = np.zeros(len(df), dtype=np.int32)

    return {
        "csi": csi,
        "timestamps_ms": timestamps,
        "node_ids": node_ids,
        "sample_rate_hz": _estimate_fs(timestamps),
        "source": str(path),
    }


def _estimate_fs(timestamps_ms: np.ndarray) -> float:
    if len(timestamps_ms) < 2:
        return 20.0
    dt = np.diff(timestamps_ms) / 1000.0
    dt = dt[(dt > 0) & (dt < 1.0)]
    if len(dt) == 0:
        return 20.0
    return float(1.0 / np.median(dt))


def load_csi_binary(path: str | Path) -> dict:
    path = Path(path)
    data = path.read_bytes()
    offset = 0
    frames = []
    timestamps = []
    node_ids = []

    while offset + HEADER_SIZE <= len(data):
        hdr = struct.unpack_from(HEADER_FMT, data, offset)
        magic, version, node_id, _, _, ts_ms, rssi, ch, sc_count, payload_bytes = hdr
        offset += HEADER_SIZE
        if magic != AURA_MAGIC:
            offset += 1
            continue
        if offset + payload_bytes > len(data):
            break
        iq = np.frombuffer(data[offset : offset + payload_bytes], dtype=np.int8)
        offset += payload_bytes
        frames.append(iq_to_complex(iq))
        timestamps.append(ts_ms)
        node_ids.append(node_id)

    if not frames:
        raise ValueError(f"No valid AURA frames in {path}")

    timestamps = np.array(timestamps, dtype=np.float64)
    return {
        "csi": np.stack(frames),
        "timestamps_ms": timestamps,
        "node_ids": np.array(node_ids, dtype=np.int32),
        "sample_rate_hz": _estimate_fs(timestamps),
        "source": str(path),
    }


def iter_csi_frames_binary(path: str | Path) -> Iterator[dict]:
    path = Path(path)
    with path.open("rb") as f:
        while True:
            hdr_bytes = f.read(HEADER_SIZE)
            if len(hdr_bytes) < HEADER_SIZE:
                break
            hdr = struct.unpack(HEADER_FMT, hdr_bytes)
            magic, _, node_id, _, _, ts_ms, _, _, _, payload_bytes = hdr
            if magic != AURA_MAGIC:
                continue
            payload = f.read(payload_bytes)
            if len(payload) < payload_bytes:
                break
            yield {
                "csi": iq_to_complex(np.frombuffer(payload, dtype=np.int8)),
                "timestamp_ms": ts_ms,
                "node_id": node_id,
            }
