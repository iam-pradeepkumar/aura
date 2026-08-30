#!/usr/bin/env python3
"""Validate AURA CSI file format before running simulation."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "simulation"))

from aura_processor.loader import load_csi_csv, load_csi_binary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csi", help="CSI .csv or .bin file")
    args = parser.parse_args()
    path = Path(args.csi)
    if path.suffix == ".bin":
        data = load_csi_binary(path)
    else:
        data = load_csi_csv(path)

    print(f"Source: {data['source']}")
    print(f"Frames: {len(data['csi'])}")
    print(f"Subcarriers: {data['csi'].shape[1]}")
    print(f"Sample rate: {data['sample_rate_hz']:.2f} Hz")
    print(f"Duration: {(data['timestamps_ms'][-1] - data['timestamps_ms'][0]) / 1000:.2f} s")
    print("OK — ready for run_simulation.py")


if __name__ == "__main__":
    main()
