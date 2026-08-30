#!/usr/bin/env python3
"""Batch-process CSI file and print sensing summary (no video)."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "simulation"))

from aura_processor import load_csi_csv, load_csi_binary, AURAPipeline
import yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csi", help="CSI .csv or .bin")
    parser.add_argument("--config", default="simulation/config.yaml")
    args = parser.parse_args()

    path = Path(args.csi)
    data = load_csi_binary(path) if path.suffix == ".bin" else load_csi_csv(path)

    cfg = {}
    cfg_path = Path(args.config)
    if cfg_path.exists():
        with cfg_path.open() as f:
            cfg = yaml.safe_load(f) or {}

    node_pos = {int(k): tuple(v) for k, v in cfg.get("node_positions", {}).items()}
    pipe = AURAPipeline(
        fs_hz=data["sample_rate_hz"],
        area_size_m=cfg.get("area_size_m", 10.0),
        node_positions=node_pos,
    )
    results = pipe.process_session(data["csi"], data["timestamps_ms"])

    print(f"Processed {len(results)} windows from {path.name}")
    for r in results:
        print(
            f"  t={r.timestamp_sec:.2f}s | motion={r.motion_detected} | "
            f"count={r.target_count} | resp={r.respiration_bpm:.1f} | hr={r.heartbeat_bpm:.1f}"
        )
        for t in r.targets:
            print(f"    Target {t.id}: ({t.x_m:.2f}, {t.y_m:.2f}) v={t.velocity_mps:.2f} m/s")
    for ev in pipe.tracker.events:
        print(f"  EVENT: {ev}")


if __name__ == "__main__":
    main()
