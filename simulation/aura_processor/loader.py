"""CSI data loaders for AURA recordings (ESP32 UART / CSV export)."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterator

import numpy as np
import pandas as pd

AURA_MAGIC = 0x41555241
HEADER_FMT = "<IBBBBIIbBHHI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)


def iq_to_complex(iq: np.ndarray) -> np.ndarray:
    """Convert interleaved int8 I/Q (Imag, Real per Espressif) to complex."""
    if iq.ndim == 1:
        imag = iq[0::2].astype(np.float32)
        real = iq[1::2].astype(np.float32)
        return real + 1j * imag
    raise ValueError("Expected 1-D interleaved I/Q buffer")


def load_csi_csv(path: str | Path) -> dict:
    """
    Load CSI exported from ESP32 host recorder.

    Expected columns:
      timestamp_ms, node_id, rssi, channel, sc0_i, sc0_q, sc1_i, sc1_q, ...
    Or: timestamp_ms, node_id, amplitude (JSON subcarriers in 'iq' column)
    """
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
    """Load AURA binary UART stream (aura_protocol.h format)."""
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
    """Stream-parse binary CSI for large recordings."""
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
