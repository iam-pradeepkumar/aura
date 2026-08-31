"""CSI data loaders — CSV, binary, .npy, .mat (Intel/csiread/WiDFS formats)."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

from .csi_orient import combine_amplitude_phase, orient_csi

AURA_MAGIC = 0x41555241
HEADER_FMT = "<IBBBBIIbBHHI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

AMP_KEYS = ("amplitude", "csi_amp", "csi_amplitude", "amp", "A", "magnitude", "mag")
PHASE_KEYS = ("phase", "csi_phase", "ph", "P", "angle", "csi_angle", "phase_rad")
CSI_KEYS = (
    "csi", "CSI", "data", "H", "csi_data", "cfm", "csi_all", "wifi_csi",
    "csi_complex", "channel_state", "cfm_data",
)
TIMESTAMP_KEYS = ("timestamp_ms", "timestamps_ms", "timestamp", "timestamps", "ts", "time", "t")


def load_csi(path: str | Path, sample_rate_hz: float | None = None) -> dict:
    """Auto-detect format from extension and file content."""
    path = Path(path)
    ext = path.suffix.lower()

    # Sniff: .npy extension may contain NPZ (zip) data
    if ext == ".npy":
        with path.open("rb") as f:
            magic = f.read(2)
        if magic == b"PK":
            return load_csi_npz(path, sample_rate_hz=sample_rate_hz)
        return load_csi_npy(path, sample_rate_hz=sample_rate_hz)

    if ext == ".bin":
        return load_csi_binary(path)
    if ext == ".csv":
        return load_csi_csv(path)
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


def _to_complex_2d(arr: np.ndarray) -> tuple[np.ndarray, dict]:
    """Normalize various CSI layouts to (frames, subcarriers) complex."""
    csi, info = orient_csi(arr)
    return csi, info


def _try_amp_phase(meta: dict) -> np.ndarray | None:
    """Build complex CSI from separate amplitude + phase fields (common in .mat exports)."""
    amp_key = next((k for k in AMP_KEYS if k in meta), None)
    ph_key = next((k for k in PHASE_KEYS if k in meta), None)
    if not amp_key or not ph_key:
        for k in meta:
            kl = k.lower()
            if amp_key is None and any(x in kl for x in ("amplitude", "csi_amp", "magnitude")):
                amp_key = k
            if ph_key is None and any(x in kl for x in ("phase", "csi_phase", "angle")):
                ph_key = k
    if amp_key and ph_key:
        return combine_amplitude_phase(np.asarray(meta[amp_key]), np.asarray(meta[ph_key]))
    return None


def _find_csi_array(meta: dict) -> tuple[np.ndarray | None, str]:
    """Locate CSI in metadata — prefer complex fields over amplitude-only."""
    combined = _try_amp_phase(meta)
    if combined is not None:
        return combined, "amplitude+phase"

    for k in CSI_KEYS:
        if k in meta and hasattr(meta[k], "shape"):
            return np.asarray(meta[k]), k

    for k in meta:
        if "csi" in k.lower() and hasattr(meta[k], "shape"):
            return np.asarray(meta[k]), k

    best, best_size, best_key = None, 0, ""
    for k, v in meta.items():
        try:
            arr = np.asarray(v)
            if arr.ndim >= 2 and arr.size > best_size:
                if k.lower() in AMP_KEYS and _try_amp_phase(meta) is None:
                    continue
                best, best_size, best_key = arr, arr.size, k
        except Exception:
            continue
    if best is not None:
        return best, best_key
    return None, ""


def _extract_timestamps(
    meta: dict,
    n_frames: int,
    sample_rate_hz: float | None,
) -> tuple[np.ndarray, float]:
    """Find timestamps in metadata dict or synthesize from sample rate."""
    for key in TIMESTAMP_KEYS:
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


CSI_KEYS_LEGACY = CSI_KEYS  # backwards compat for internal refs


def _meta_from_npz(data: np.lib.npyio.NpzFile) -> dict:
    return {k: data[k] for k in data.files}


def _find_csi_key(meta: dict) -> str | None:
    arr, key = _find_csi_array(meta)
    return key if arr is not None else None


def _pack_load_result(
    csi: np.ndarray,
    orient_info: dict,
    meta: dict,
    n_frames: int,
    sample_rate_hz: float | None,
    source: str,
    source_field: str = "",
) -> dict:
    timestamps, fs = _extract_timestamps(meta, n_frames, sample_rate_hz)
    node_ids = _extract_node_ids(meta, n_frames)
    load_info = {
        "source_field": source_field,
        "format": Path(source).suffix.lower(),
        **orient_info,
    }
    return {
        "csi": csi,
        "timestamps_ms": timestamps,
        "node_ids": node_ids,
        "sample_rate_hz": fs,
        "source": source,
        "load_info": load_info,
    }


def _align_csi_pair(
    mat_csi: np.ndarray,
    npy_amp: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Trim/pad mat and npy amplitude arrays to a common (frames, subcarriers) shape."""
    mat_csi = np.asarray(mat_csi)
    npy_amp = np.asarray(npy_amp, dtype=np.float64)
    if np.iscomplexobj(npy_amp):
        npy_amp = np.abs(npy_amp)

    n_frames = min(mat_csi.shape[0], npy_amp.shape[0])
    sc = min(mat_csi.shape[1], npy_amp.shape[1])
    return mat_csi[:n_frames, :sc], npy_amp[:n_frames, :sc]


def merge_csi_mat_npy(
    mat_data: dict,
    npy_data: dict,
    sample_rate_hz: float | None = None,
) -> dict:
    """
    Fuse one dataset's .mat (complex CSI with phase) and .npy (amplitude-only).

    Phase comes from .mat; magnitude is taken from the preprocessed .npy so motion
    energy matches the lab pipeline while localization/vitals keep phase information.
    """
    mat_csi = mat_data["csi"]
    npy_raw = npy_data["csi"]
    mat_csi, npy_amp = _align_csi_pair(mat_csi, npy_raw)

    if mat_csi.size == 0 or npy_amp.size == 0:
        raise ValueError("Empty CSI after aligning .mat and .npy shapes")

    phase = np.angle(mat_csi)
    fused = (npy_amp * np.exp(1j * phase)).astype(np.complex64)

    n = len(fused)
    mat_ts = np.asarray(mat_data.get("timestamps_ms", []), dtype=np.float64).ravel()
    npy_ts = np.asarray(npy_data.get("timestamps_ms", []), dtype=np.float64).ravel()
    if len(mat_ts) >= n:
        timestamps = mat_ts[:n]
        fs = float(mat_data.get("sample_rate_hz", 20.0))
    elif len(npy_ts) >= n:
        timestamps = npy_ts[:n]
        fs = float(npy_data.get("sample_rate_hz", 20.0))
    else:
        fs = sample_rate_hz or float(mat_data.get("sample_rate_hz") or npy_data.get("sample_rate_hz") or 1000.0)
        timestamps = np.arange(n, dtype=np.float64) * (1000.0 / fs)

    if sample_rate_hz:
        fs = float(sample_rate_hz)
    elif len(timestamps) >= 2:
        fs = _estimate_fs(timestamps)

    mat_ids = np.asarray(mat_data.get("node_ids", np.zeros(n)), dtype=np.int32).ravel()
    node_ids = mat_ids[:n] if len(mat_ids) >= n else np.zeros(n, dtype=np.int32)

    mat_info = mat_data.get("load_info", {})
    npy_info = npy_data.get("load_info", {})
    orient_info = {
        **mat_info,
        "merged_with_npy": True,
        "mat_frames": int(mat_data["csi"].shape[0]),
        "npy_frames": int(npy_data["csi"].shape[0]),
        "fused_frames": n,
        "fused_subcarriers": int(fused.shape[1]),
        "amplitude_source": "npy",
        "phase_source": "mat",
        "npy_source_field": npy_info.get("source_field", ""),
        "has_phase": bool(np.std(phase) > 1e-4),
        "n_frames": n,
        "n_subcarriers": int(fused.shape[1]),
        "output_shape": fused.shape,
    }

    return {
        "csi": fused,
        "timestamps_ms": timestamps,
        "node_ids": node_ids,
        "sample_rate_hz": fs,
        "source": f"{mat_data.get('source', 'mat')}+{npy_data.get('source', 'npy')}",
        "load_info": orient_info,
        "mat_csi": mat_csi,
        "npy_amplitude": npy_amp,
    }


def load_csi_npy(path: str | Path, sample_rate_hz: float | None = None) -> dict:
    """
    Load .npy CSI array (also handles misnamed .npz files).
    """
    path = Path(path)
    raw = np.load(path, allow_pickle=True)

    # NPZ saved with .npy extension
    if isinstance(raw, np.lib.npyio.NpzFile):
        return load_csi_npz(path, sample_rate_hz=sample_rate_hz)

    meta: dict = {}
    csi_key = "array"
    if isinstance(raw, np.ndarray) and raw.dtype == object:
        item = raw.item()
        if isinstance(item, dict):
            meta = item
            raw, source_field = _find_csi_array(meta)
            if raw is None:
                raise ValueError(f".npy dict must contain CSI array. Keys: {list(meta.keys())}")
            arr = raw
            csi_key = source_field
        else:
            arr = item
    else:
        arr = raw
        meta_path = path.with_name(path.stem + "_meta.npy")
        if meta_path.exists():
            meta_obj = np.load(meta_path, allow_pickle=True)
            if isinstance(meta_obj, np.lib.npyio.NpzFile):
                meta = _meta_from_npz(meta_obj)
            elif isinstance(meta_obj, np.ndarray) and meta_obj.dtype == object:
                meta = meta_obj.item() if isinstance(meta_obj.item(), dict) else {"meta": meta_obj}
            else:
                meta = {"meta": meta_obj}

    csi, orient_info = _to_complex_2d(arr)
    return _pack_load_result(
        csi, orient_info, meta, len(csi), sample_rate_hz, str(path),
        source_field=csi_key or "array",
    )


def load_csi_npz(path: str | Path, sample_rate_hz: float | None = None) -> dict:
    """Load .npz with keys like csi, timestamp_ms, node_id."""
    path = Path(path)
    data = np.load(path, allow_pickle=True)
    meta = _meta_from_npz(data)
    raw, source_field = _find_csi_array(meta)
    if raw is None:
        raise ValueError(f".npz must contain CSI array. Found keys: {list(meta.keys())}")
    csi, orient_info = _to_complex_2d(raw)
    orient_info["source_field"] = source_field
    return _pack_load_result(
        csi, orient_info, meta, len(csi), sample_rate_hz, str(path), source_field=source_field,
    )


def _mat_file_kind(path: Path) -> str:
    """
    Classify .mat files:
    - mat73: MATLAB 7.3 HDF5-based .mat
    - hdf5: plain HDF5 saved with .mat extension
    - scipy: MATLAB v4/v5/v6/v7.2
    """
    with path.open("rb") as f:
        head = f.read(128)
    if head.startswith(b"\x89HDF\r\n"):
        return "hdf5"
    if head.startswith(b"MATLAB 7.3") or (len(head) > 125 and head[124:126] == b"\x00\x02"):
        return "mat73"
    return "scipy"


def _is_hdf5_file(path: Path) -> bool:
    return _mat_file_kind(path) in ("hdf5", "mat73")


def _h5_read_node(obj) -> object:
    """Read one HDF5 dataset or group into numpy / nested dict."""
    import h5py

    if isinstance(obj, h5py.Dataset):
        data = obj[()]
        if getattr(data, "dtype", None) is not None and data.dtype.names:
            if "real" in data.dtype.names and "imag" in data.dtype.names:
                arr = data["real"] + 1j * data["imag"]
            else:
                arr = np.array(data)
        else:
            arr = np.array(data)
        if isinstance(arr, np.ndarray) and arr.ndim >= 2 and np.issubdtype(arr.dtype, np.number):
            arr = arr.T
        return arr

    if isinstance(obj, h5py.Group):
        if "real" in obj and "imag" in obj:
            real = np.array(obj["real"][()])
            imag = np.array(obj["imag"][()])
            arr = real + 1j * imag
            if arr.ndim >= 2:
                arr = arr.T
            return arr
        out: dict = {}
        for key in obj.keys():
            out[key] = _h5_read_node(obj[key])
        return out

    return None


def _flatten_mat_meta(meta: dict, prefix: str = "") -> dict:
    """Flatten nested dicts from HDF5 groups so CSI fields are discoverable."""
    flat: dict = {}
    for key, val in meta.items():
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            flat.update(_flatten_mat_meta(val, full))
        else:
            flat[full] = val
    return flat


def _load_mat_h5(path: Path) -> dict:
    """MATLAB v7.3 HDF5 .mat files and plain HDF5 CSI exports."""
    if _mat_file_kind(path) == "mat73":
        try:
            import mat73

            return mat73.loadmat(str(path))
        except Exception:
            pass

    import h5py

    meta: dict = {}
    with h5py.File(path, "r") as f:
        for key in f.keys():
            if key.startswith("#"):
                continue
            meta[key] = _h5_read_node(f[key])

    if not meta:
        raise ValueError(f"No variables found in HDF5 file {path.name}")
    return meta


def _load_mat_meta(path: Path) -> dict:
    kind = _mat_file_kind(path)
    if kind in ("hdf5", "mat73"):
        return _load_mat_h5(path)

    from scipy.io import loadmat

    try:
        mat = loadmat(path, squeeze_me=True, struct_as_record=False)
        return {k: v for k, v in mat.items() if not k.startswith("__")}
    except NotImplementedError:
        return _load_mat_h5(path)
    except ValueError as exc:
        if "Unknown mat file type" in str(exc):
            return _load_mat_h5(path)
        raise


def load_csi_mat(path: str | Path, sample_rate_hz: float | None = None) -> dict:
    """
    Load .mat CSI — complex arrays, separate amplitude+phase, Intel/csiread layouts.
    Supports (antennas, subcarriers, packets) and (packets, subcarriers) orientations.
    """
    path = Path(path)

    try:
        meta = _flatten_mat_meta(_load_mat_meta(path))
    except Exception as primary_exc:
        try:
            return _load_mat_csiread(path, sample_rate_hz)
        except ImportError:
            raise primary_exc
        except Exception:
            raise primary_exc from None

    raw, source_field = _find_csi_array(meta)
    if raw is None:
        try:
            return _load_mat_csiread(path, sample_rate_hz)
        except ImportError:
            pass
        except Exception:
            pass
        raise ValueError(
            f"No CSI in {path.name}. Need complex 'csi', or amplitude+phase fields. "
            f"Found keys: {list(meta.keys())}"
        )

    orient_info: dict = {"source_field": source_field, "mat_loader": "hdf5" if _is_hdf5_file(path) else "scipy"}

    if isinstance(raw, np.ndarray) and raw.dtype == object:
        frames: list[np.ndarray] = []
        infos: list[dict] = []
        for cell in raw.ravel():
            f, inf = _to_complex_2d(np.asarray(cell))
            frames.append(f)
            infos.append(inf)
        max_sc = max(f.shape[1] for f in frames)
        csi = np.stack([
            np.pad(f, ((0, 0), (0, max_sc - f.shape[1])), mode="edge") for f in frames
        ])
        orient_info = {"cell_array": True, "n_cells": len(frames), **infos[0]}
    else:
        csi, orient_info = _to_complex_2d(np.asarray(raw))
        orient_info["source_field"] = source_field

    return _pack_load_result(
        csi, orient_info, meta, len(csi), sample_rate_hz, str(path), source_field=source_field,
    )


def _load_mat_csiread(path: Path, sample_rate_hz: float | None) -> dict:
    import csiread

    reader = csiread.Intel(str(path))
    reader.read()
    csi, orient_info = _to_complex_2d(reader.csi)
    meta: dict = {}
    if hasattr(reader, "timestamp") and len(reader.timestamp) == len(csi):
        meta["timestamp"] = reader.timestamp
    return _pack_load_result(
        csi, {**orient_info, "loader": "csiread"}, meta, len(csi), sample_rate_hz, str(path),
        source_field="csiread",
    )


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
