#!/usr/bin/env python3
"""Record CSI from AURA ESP32 RX node over UART to CSV."""

from __future__ import annotations

import argparse
import struct
import sys
import time
from pathlib import Path

import numpy as np

HEADER_FMT = "<IBBBBIIbBHHI"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
AURA_MAGIC = 0x41555241


def record_binary(port: str, baud: int, duration_sec: float, out_path: Path):
    import serial

    ser = serial.Serial(port, baud, timeout=1)
    print(f"Recording from {port} for {duration_sec}s → {out_path}")
    start = time.time()
    raw = bytearray()

    try:
        while time.time() - start < duration_sec:
            chunk = ser.read(4096)
            if chunk:
                raw.extend(chunk)
    finally:
        ser.close()

    out_path.write_bytes(raw)
    print(f"Saved {len(raw)} bytes ({out_path})")
    export_csv_from_binary(raw, out_path.with_suffix(".csv"))


def export_csv_from_binary(raw: bytes, csv_path: Path):
    """Convert binary stream to CSV for simulation viewer."""
    offset = 0
    rows = []
    max_sc = 0

    while offset + HEADER_SIZE <= len(raw):
        hdr = struct.unpack_from(HEADER_FMT, raw, offset)
        magic, _, node_id, _, _, ts_ms, rssi, ch, sc_count, payload_bytes = hdr
        offset += HEADER_SIZE
        if magic != AURA_MAGIC:
            offset += 1
            continue
        if offset + payload_bytes > len(raw):
            break
        iq = np.frombuffer(raw[offset : offset + payload_bytes], dtype=np.int8)
        offset += payload_bytes
        max_sc = max(max_sc, len(iq) // 2)
        rows.append((ts_ms, node_id, rssi, ch, iq.tolist()))

    if not rows:
        print("Warning: no frames parsed", file=sys.stderr)
        return

    with csv_path.open("w") as f:
        header = ["timestamp_ms", "node_id", "rssi", "channel", "iq"]
        f.write(",".join(header) + "\n")
        for ts_ms, node_id, rssi, ch, iq_list in rows:
            f.write(f"{ts_ms},{node_id},{rssi},{ch},\"{iq_list}\"\n")
    print(f"Exported CSV: {csv_path} ({len(rows)} frames)")


def main():
    parser = argparse.ArgumentParser(description="Record AURA CSI from ESP32 UART")
    parser.add_argument("-p", "--port", required=True, help="Serial port e.g. /dev/ttyUSB0")
    parser.add_argument("-d", "--duration", type=float, default=3.0, help="Seconds to record")
    parser.add_argument("-o", "--output", default="session.bin", help="Output binary path")
    parser.add_argument("-b", "--baud", type=int, default=921600)
    args = parser.parse_args()

    record_binary(args.port, args.baud, args.duration, Path(args.output))


if __name__ == "__main__":
    main()
