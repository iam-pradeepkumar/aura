#!/usr/bin/env python3
"""Run full mobile SAR mission (standalone kinematic sim — no Gazebo required)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from bootstrap import bootstrap

ROOT = bootstrap()

from aura_processor.mobile_field import create_mobile_engine
from aura_sim_core.mission import MobileMissionController
from aura_sim_core.bridge import frame_to_bridge_message


def main() -> int:
    parser = argparse.ArgumentParser(description="AURA mobile mission (standalone)")
    parser.add_argument("--config", default=str(ROOT / "simulation" / "config.yaml"))
    parser.add_argument("--zone", default=str(ROOT / "gazebo_sim" / "config" / "disaster_zone.yaml"))
    parser.add_argument("--max-sec", type=float, default=180.0)
    parser.add_argument("--json-log", default="")
    args = parser.parse_args()

    mission = MobileMissionController.from_config(args.zone)
    engine = create_mobile_engine(args.config)
    engine.config["area_size_m"] = mission.world.area_size_m

    tick_hz = 10.0
    dt = 1.0 / tick_hz
    packets = 24
    t0 = time.time()
    last_frame = None

    print("AURA mobile mission — standalone kinematic sim")
    print(f"Zone {mission.world.area_size_m}m | rover WPs {len(mission.rover_waypoints)} | drone WPs {len(mission.drone_waypoints)}")

    while time.time() - t0 < args.max_sec and not mission.stats.completed:
        status = mission.tick(dt)
        engine.update_node_positions(mission.node_positions())
        mission.inject_csi(engine.rx, packets=packets)
        last_frame = engine.process_frame()
        if int(status["elapsed_sec"]) % 5 == 0 and status["elapsed_sec"] > 0:
            print(
                f"  t={status['elapsed_sec']}s phase={status['phase']} "
                f"cov={status['coverage_pct']}% det={status['confirmed_detections']} "
                f"targets={last_frame.get('target_count', 0) if last_frame else 0}"
            )
        time.sleep(dt)

    elapsed = time.time() - t0
    summary = {
        "mission_time_sec": round(elapsed, 1),
        "coverage_pct": mission.stats.coverage_pct,
        "confirmed_detections": mission.stats.confirmed_detections,
        "completed": mission.stats.completed,
        "final_targets": last_frame.get("target_count", 0) if last_frame else 0,
    }
    print("\nMission summary:", json.dumps(summary, indent=2))
    if args.json_log:
        Path(args.json_log).write_text(json.dumps(summary, indent=2))
    if last_frame:
        bridge = frame_to_bridge_message(last_frame, status)
        print("Bridge sample keys:", list(bridge.keys()))
    return 0 if mission.stats.completed or mission.stats.confirmed_detections > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
