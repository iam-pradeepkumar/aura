#!/usr/bin/env python3
"""Validate AURA CSI file (.npy, .mat, .csv, .bin) before simulation."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "simulation"))

from aura_processor import load_csi


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csi", help="CSI file (.npy, .mat, .npz, .csv, .bin)")
    parser.add_argument("--fs", type=float, default=None, help="Sample rate if not in file")
    args = parser.parse_args()

    data = load_csi(args.csi, sample_rate_hz=args.fs)
    dur = (data["timestamps_ms"][-1] - data["timestamps_ms"][0]) / 1000.0 if len(data["timestamps_ms"]) > 1 else 0

    print(f"Source:      {data['source']}")
    print(f"Frames:      {len(data['csi'])}")
    print(f"Subcarriers: {data['csi'].shape[1]}")
    print(f"Sample rate: {data['sample_rate_hz']:.2f} Hz")
    print(f"Duration:    {dur:.2f} s")
    print("OK — ready for: python simulation/run_simulation.py --video YOUR.mp4 --csi", args.csi)


if __name__ == "__main__":
    main()
