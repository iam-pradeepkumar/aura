#!/usr/bin/env python3
"""Record CSI from AURA ESP32 RX node over UART to binary/CSV."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "simulation"))
from aura_processor.aura_protocol import AURA_MAGIC, HEADER_SIZE, unpack_header


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
    """Convert binary stream to CSV for offline replay."""
    offset = 0
    rows = []

    while offset + HEADER_SIZE <= len(raw):
        hdr = unpack_header(raw, offset)
        magic, version, node_id, link_id, reserved, ts_ms, rssi, ch, sc_count, payload_bytes = hdr
        offset += HEADER_SIZE
        if magic != AURA_MAGIC:
            offset += 1
            continue
        if offset + payload_bytes > len(raw):
            break
        iq = np.frombuffer(raw[offset : offset + payload_bytes], dtype=np.int8)
        offset += payload_bytes
        rows.append((ts_ms, node_id, rssi, ch, iq.tolist()))

    if not rows:
        print("No frames found in recording")
        return

    import csv

    with csv_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp_ms", "node_id", "rssi", "channel", "iq"])
        w.writerows(rows)
    print(f"Exported {len(rows)} frames → {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="Record AURA CSI from UART")
    parser.add_argument("--port", required=True, help="Serial port e.g. /dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--out", default="session.bin")
    args = parser.parse_args()
    record_binary(args.port, args.baud, args.duration, Path(args.out))


if __name__ == "__main__":
    main()
